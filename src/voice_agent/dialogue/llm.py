"""LLM arayüzü. Sağlayıcıdan bağımsızdır; testler betikli bir sahte LLM kullanır."""

from collections.abc import Callable, Sequence
from typing import Protocol

from voice_agent.dialogue.models import ConversationState, LLMDecision, LLMRequest, ToolSpec
from voice_agent.dialogue.policy import ALLOWED_TOOLS
from voice_agent.tools.schemas import TOOL_ARGS


class LLM(Protocol):
    def decide(self, request: LLMRequest) -> LLMDecision:
        """Verilen duruma göre yanıt, araç çağrısı veya niyet üretir."""
        ...


def tool_specs(state: ConversationState) -> list[ToolSpec]:
    """Yalnızca mevcut aşamada izinli araçların tanımlarını döndürür."""
    specs: list[ToolSpec] = []
    for name in sorted(ALLOWED_TOOLS[state.phase]):
        model = TOOL_ARGS[name]
        specs.append(
            ToolSpec(
                name=name,
                description=(model.__doc__ or "").strip(),
                parameters=model.model_json_schema(),
            )
        )
    return specs


def build_request(state: ConversationState) -> LLMRequest:
    return LLMRequest(
        phase=state.phase,
        allowed_tools=tool_specs(state),
        messages=list(state.messages),
        customer_name=state.customer_name,
        authenticated=state.authenticated,
    )


Step = LLMDecision | Callable[[LLMRequest], LLMDecision]


class ScriptedLLM:
    """Önceden yazılmış kararları sırayla döndürür. Gelen istekleri kaydeder."""

    def __init__(self, steps: Sequence[Step]) -> None:
        self._steps = list(steps)
        self.requests: list[LLMRequest] = []

    def decide(self, request: LLMRequest) -> LLMDecision:
        self.requests.append(request)
        if not self._steps:
            raise AssertionError("ScriptedLLM: beklenmeyen ek çağrı")
        step = self._steps.pop(0)
        return step(request) if callable(step) else step
