import pytest

from voice_agent.evaluation.wer import corpus_wer, normalize_tr, word_errors


def test_normalize_turkish_case_and_punctuation() -> None:
    assert normalize_tr("IŞIK yanmıyor, İSTANBUL'da!") == "ışık yanmıyor istanbul da"


@pytest.mark.parametrize(
    ("ref", "hyp", "errors"),
    [
        ("modemim ışık yakmıyor", "modemim ışık yakmıyor", 0),
        ("modemim ışık yakmıyor", "modemim yakmıyor", 1),  # silme
        ("modemim ışık yakmıyor", "modemim ışık hiç yakmıyor", 1),  # ekleme
        ("faturam yüksek", "faturan yüksek", 1),  # değiştirme
        ("", "bir şey", 2),  # yalnızca ekleme
    ],
)
def test_word_errors(ref: str, hyp: str, errors: int) -> None:
    assert word_errors(ref, hyp).errors == errors


def test_corpus_wer_weights_by_reference_length() -> None:
    pairs = [("a b c d", "a b c d"), ("e f", "e x")]
    assert corpus_wer(pairs) == pytest.approx(1 / 6)
