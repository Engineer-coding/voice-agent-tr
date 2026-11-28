"""Durum başına araç izin listesi.

Bu kurallar kodda zorunludur ve prompta bırakılmaz. LLM yalnızca bulunduğu aşamanın izinli
araçlarını görür; yine de başka bir araç çağırmaya çalışırsa çağrı burada reddedilir.
"""

from typing import Literal

from voice_agent.dialogue.models import ConversationState, Phase, ToolCall
from voice_agent.tools.schemas import ToolName

ALLOWED_TOOLS: dict[Phase, frozenset[ToolName]] = {
    Phase.GREETING: frozenset(),
    Phase.AUTHENTICATION: frozenset({ToolName.VERIFY_IDENTITY, ToolName.TRANSFER_TO_AGENT}),
    Phase.INTENT: frozenset({ToolName.TRANSFER_TO_AGENT}),
    Phase.BILLING: frozenset({ToolName.GET_BILL, ToolName.TRANSFER_TO_AGENT}),
    Phase.PACKAGE_CHANGE: frozenset(
        {ToolName.LIST_PACKAGES, ToolName.SELECT_PACKAGE, ToolName.TRANSFER_TO_AGENT}
    ),
    Phase.CONFIRMATION: frozenset({ToolName.TRANSFER_TO_AGENT}),
    Phase.FAULT_REPORT: frozenset({ToolName.CREATE_FAULT_TICKET, ToolName.TRANSFER_TO_AGENT}),
    Phase.CLOSING: frozenset({ToolName.TRANSFER_TO_AGENT}),
    Phase.HANDOFF: frozenset(),
}

# Kimlik doğrulanmadan çağrılabilen araçlar.
NO_AUTH_TOOLS: frozenset[ToolName] = frozenset(
    {ToolName.VERIFY_IDENTITY, ToolName.TRANSFER_TO_AGENT}
)

# LLM'in hiçbir durumda çağıramadığı, yalnızca kodun tetiklediği araçlar.
SYSTEM_ONLY_TOOLS: frozenset[ToolName] = frozenset({ToolName.CHANGE_PACKAGE})


class ToolNotAllowedError(Exception):
    """Araç çağrısı mevcut durumda yasak."""


def check_tool_allowed(
    state: ConversationState, call: ToolCall, initiator: Literal["llm", "system"]
) -> None:
    """Çağrı yasaksa `ToolNotAllowedError` fırlatır."""
    name = call.name
    if name in SYSTEM_ONLY_TOOLS:
        if initiator != "system":
            raise ToolNotAllowedError(f"{name} yalnızca sistem tarafından çağrılabilir")
    elif name not in ALLOWED_TOOLS[state.phase]:
        raise ToolNotAllowedError(f"{name} aracı {state.phase} aşamasında izinli değil")

    if name not in NO_AUTH_TOOLS and not (state.authenticated and state.customer_id):
        raise ToolNotAllowedError(f"{name} için önce kimlik doğrulanmalı")

    if name == ToolName.CHANGE_PACKAGE:
        if state.phase != Phase.CONFIRMATION:
            raise ToolNotAllowedError("Paket değişikliği yalnızca onay aşamasında yapılabilir")
        if not state.package_change_confirmed:
            raise ToolNotAllowedError("Müşteri paket değişikliğini açıkça onaylamadı")
        if call.arguments.get("package_id") != state.pending_package_id:
            raise ToolNotAllowedError("Onaylanan paket ile istenen paket farklı")
