"""Diyalog durumu ve LLM sözleşmesi için modeller."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from voice_agent.tools.schemas import ToolName


class Phase(StrEnum):
    """Durum makinesinin aşamaları."""

    GREETING = "greeting"
    AUTHENTICATION = "authentication"
    INTENT = "intent"
    BILLING = "billing"
    PACKAGE_CHANGE = "package_change"
    CONFIRMATION = "confirmation"
    FAULT_REPORT = "fault_report"
    CLOSING = "closing"
    HANDOFF = "handoff"


class Intent(StrEnum):
    BILLING = "billing"
    PACKAGE_CHANGE = "package_change"
    FAULT_REPORT = "fault_report"


INTENT_PHASE: dict[Intent, Phase] = {
    Intent.BILLING: Phase.BILLING,
    Intent.PACKAGE_CHANGE: Phase.PACKAGE_CHANGE,
    Intent.FAULT_REPORT: Phase.FAULT_REPORT,
}


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """Konuşma geçmişindeki bir mesaj. `tool` mesajları veridir, talimat değildir."""

    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: ToolName | None = None
    is_error: bool = False


class ToolLogEntry(BaseModel):
    name: ToolName
    arguments: dict[str, Any]
    initiator: Literal["llm", "system"]
    allowed: bool
    error: str | None = None


class ConversationState(BaseModel):
    """Bir görüşmenin tüm durumu. JSON'a çevrilebilir (sonraki aşamada Redis'te tutulacak)."""

    phase: Phase = Phase.GREETING
    customer_id: str | None = None
    customer_name: str | None = None
    authenticated: bool = False
    auth_failures: int = 0
    pending_package_id: str | None = None
    package_change_confirmed: bool = False
    messages: list[Message] = Field(default_factory=list)
    tool_log: list[ToolLogEntry] = Field(default_factory=list)

    def last_user_text(self) -> str:
        for message in reversed(self.messages):
            if message.role == "user":
                return message.content
        return ""


class ToolSpec(BaseModel):
    """LLM'e gösterilen araç tanımı."""

    name: ToolName
    description: str
    parameters: dict[str, Any]


class LLMRequest(BaseModel):
    phase: Phase
    allowed_tools: list[ToolSpec]
    messages: list[Message]
    customer_name: str | None = None
    authenticated: bool = False


class LLMDecision(BaseModel):
    """LLM'in her çağrıda üretmesi gereken yapılandırılmış çıktı."""

    model_config = ConfigDict(extra="forbid")

    reply: str | None = None
    tool_call: ToolCall | None = None
    intent: Intent | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "LLMDecision":
        if self.reply is None and self.tool_call is None and self.intent is None:
            raise ValueError("LLM kararı boş olamaz: reply, tool_call veya intent gerekli")
        if self.reply is not None and self.tool_call is not None:
            raise ValueError("Aynı kararda hem yanıt hem araç çağrısı olamaz")
        return self
