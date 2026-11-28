"""STT çıktısına dayanıklılık: rakam biçimleri ve kimlik doğrulama hatasında geri okuma."""

from collections.abc import Callable
from datetime import date

import pytest

from voice_agent.dialogue.agent import DialogueAgent
from voice_agent.dialogue.rule_based import find_birth_date, format_phone


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("14.05.1990", date(1990, 5, 14)),
        ("14 05 1990", date(1990, 5, 14)),  # Whisper small böyle yazdı
        ("05 223 45 67 14 05 1990", date(1990, 5, 14)),
        ("14 Mayıs 1990", date(1990, 5, 14)),
        ("45 67 1990", None),
        ("31.02.1990", None),
    ],
)
def test_birth_date_formats(text: str, expected: date | None) -> None:
    assert find_birth_date(text) == expected


def test_format_phone_groups_digits_for_reading() -> None:
    assert format_phone("05322234567") == "0532 223 45 67"


def test_failed_verification_reads_back_what_was_heard(
    make_agent: Callable[..., DialogueAgent],
) -> None:
    """STT numarayı yanlış duyarsa müşteri neyin yanlış anlaşıldığını duyabilmeli."""
    agent = make_agent()
    reply = agent.handle("0532 223 45 67, 14 05 1990")
    assert "eşleşmedi" in reply
    assert "0532 223 45 67" in reply
    assert "14 Mayıs 1990" in reply
    assert "yazabilirsiniz" in reply
