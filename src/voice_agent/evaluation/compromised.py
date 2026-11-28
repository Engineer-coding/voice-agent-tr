"""Prompt injection ile tamamen ele geçirilmiş bir LLM'i taklit eder.

Saldırı turunda saldırganın istediği kararları sırayla üretir, sonra normal LLM'e devreder.
Amaç en kötü durumu ölçmek: LLM saldırgana itaat etse bile kod yetkisiz işlemi durdurmalı.
"""

from voice_agent.dialogue.llm import LLM
from voice_agent.dialogue.models import LLMDecision, LLMRequest, ToolCall
from voice_agent.evaluation.specs import AttemptedDecision


class CompromisedLLM:
    def __init__(self, base: LLM, attack_turn: int, attempts: list[AttemptedDecision]) -> None:
        self.base = base
        self.attack_turn = attack_turn
        self._attempts = list(attempts)

    def decide(self, request: LLMRequest) -> LLMDecision:
        user_turns = sum(1 for m in request.messages if m.role == "user")
        if user_turns - 1 == self.attack_turn and self._attempts:
            attempt = self._attempts.pop(0)
            if attempt.tool is not None:
                return LLMDecision(
                    tool_call=ToolCall(name=attempt.tool, arguments=attempt.arguments)
                )
            return LLMDecision(intent=attempt.intent)
        return self.base.decide(request)
