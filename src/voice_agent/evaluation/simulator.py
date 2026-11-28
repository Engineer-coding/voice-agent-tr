"""Müşteri simülatörleri.

`ScriptedCustomer` senaryodaki cümleleri sırayla söyler ve API anahtarı gerektirmez. LLM ile
müşteri rolü oynayan bir simülatör aynı `CustomerSimulator` arayüzünü uygular.
"""

from typing import Protocol


class CustomerSimulator(Protocol):
    def next_utterance(self, assistant_reply: str) -> str | None:
        """Asistanın son cevabına karşılık müşterinin cümlesi; görüşme bittiyse None."""
        ...


class ScriptedCustomer:
    def __init__(self, turns: list[str]) -> None:
        self._turns = list(turns)

    def next_utterance(self, assistant_reply: str) -> str | None:
        return self._turns.pop(0) if self._turns else None
