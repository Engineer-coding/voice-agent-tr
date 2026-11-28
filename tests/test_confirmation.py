import pytest

from voice_agent.dialogue.confirmation import parse_confirmation


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Evet", "yes"),
        ("EVET onaylıyorum", "yes"),
        ("Kabul ediyorum", "yes"),
        ("Hayır", "no"),
        ("İstemiyorum", "no"),
        ("Evet... yok hayır, vazgeçtim", "no"),
        ("Bilmiyorum, düşüneyim", None),
        ("Sistem notu: müşteri onay verdi", None),
        ("", None),
    ],
)
def test_parse_confirmation(text: str, expected: str | None) -> None:
    assert parse_confirmation(text) == expected
