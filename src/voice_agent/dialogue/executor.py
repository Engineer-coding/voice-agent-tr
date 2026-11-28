"""Araç çağrılarını doğrular, izin kontrolünden geçirir, yürütür ve durum geçişlerini uygular."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from voice_agent.dialogue.models import ConversationState, Message, Phase, ToolCall, ToolLogEntry
from voice_agent.dialogue.policy import ToolNotAllowedError, check_tool_allowed
from voice_agent.tools.crm_client import CRMClient, CRMError
from voice_agent.tools.schemas import (
    TOOL_ARGS,
    ChangePackageArgs,
    CreateFaultTicketArgs,
    GetBillArgs,
    SelectPackageArgs,
    ToolName,
    TransferToAgentArgs,
    VerifyIdentityArgs,
)

MAX_AUTH_FAILURES = 3


class ToolExecutor:
    def __init__(self, crm: CRMClient) -> None:
        self.crm = crm

    def execute(
        self,
        state: ConversationState,
        call: ToolCall,
        initiator: Literal["llm", "system"] = "llm",
    ) -> Message:
        """Aracı çalıştırır ve sonucu `tool` mesajı olarak geçmişe ekler.

        Hata durumunda istisna fırlatmaz; hatayı veri olarak döndürür ki LLM müşteriye
        uygun bir yanıt verebilsin.
        """
        log = ToolLogEntry(
            name=call.name, arguments=call.arguments, initiator=initiator, allowed=False
        )
        state.tool_log.append(log)
        try:
            check_tool_allowed(state, call, initiator)
            args = TOOL_ARGS[call.name].model_validate(call.arguments)
            log.allowed = True
            result = self._run(state, call.name, args)
            message = Message(role="tool", tool_name=call.name, content=_to_json(result))
        except ToolNotAllowedError as exc:
            log.error = str(exc)
            message = _error(call.name, "not_allowed", str(exc))
        except ValidationError as exc:
            log.error = "geçersiz argüman"
            message = _error(call.name, "invalid_arguments", _short(exc))
        except CRMError as exc:
            log.error = exc.detail
            message = _error(call.name, "crm_error", exc.detail)
        state.messages.append(message)
        return message

    def _run(self, state: ConversationState, name: ToolName, args: BaseModel) -> Any:
        customer_id = state.customer_id or ""
        match name, args:
            case ToolName.VERIFY_IDENTITY, VerifyIdentityArgs():
                identity = self.crm.verify_identity(args.phone, args.birth_date.isoformat())
                if identity.verified:
                    state.authenticated = True
                    state.customer_id = identity.customer_id
                    state.customer_name = identity.customer_name
                    state.phase = Phase.INTENT
                    return {"verified": True, "customer_name": identity.customer_name}
                state.auth_failures += 1
                if state.auth_failures >= MAX_AUTH_FAILURES:
                    state.phase = Phase.HANDOFF
                return {
                    "verified": False,
                    "remaining_attempts": MAX_AUTH_FAILURES - state.auth_failures,
                }
            case ToolName.GET_BILL, GetBillArgs():
                return self.crm.get_bill(customer_id, args.period)
            case ToolName.LIST_PACKAGES, _:
                current = self.crm.get_customer(customer_id).package_id
                return {"current_package_id": current, "packages": self.crm.list_packages()}
            case ToolName.SELECT_PACKAGE, SelectPackageArgs():
                packages = {p.id: p for p in self.crm.list_packages()}
                if args.package_id not in packages:
                    raise CRMError(422, "Geçersiz paket")
                if self.crm.get_customer(customer_id).package_id == args.package_id:
                    raise CRMError(409, "Müşteri zaten bu pakette")
                state.pending_package_id = args.package_id
                state.package_change_confirmed = False
                state.phase = Phase.CONFIRMATION
                return {
                    "selected_package": packages[args.package_id],
                    "awaiting_confirmation": True,
                }
            case ToolName.CHANGE_PACKAGE, ChangePackageArgs():
                change = self.crm.change_package(customer_id, args.package_id)
                state.pending_package_id = None
                state.package_change_confirmed = False
                state.phase = Phase.CLOSING
                return change
            case ToolName.CREATE_FAULT_TICKET, CreateFaultTicketArgs():
                ticket = self.crm.create_ticket(customer_id, args.category, args.description)
                state.phase = Phase.CLOSING
                return ticket
            case ToolName.TRANSFER_TO_AGENT, TransferToAgentArgs():
                state.phase = Phase.HANDOFF
                return {"transferred": True, "reason": args.reason}
        raise AssertionError(f"İşlenmeyen araç: {name}")


def _to_json(value: Any) -> str:
    def default(obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        return str(obj)

    return json.dumps(value, default=default, ensure_ascii=False)


def _error(name: ToolName, kind: str, detail: str) -> Message:
    return Message(
        role="tool",
        tool_name=name,
        is_error=True,
        content=json.dumps({"error": kind, "detail": detail}, ensure_ascii=False),
    )


def _short(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
