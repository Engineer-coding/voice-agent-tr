"""Kelime hata oranı (WER). Türkçe büyük/küçük harf kurallarıyla normalleştirir."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

_PUNCT = re.compile(r"[^\w\s]")


def normalize_tr(text: str) -> str:
    """Türkçe küçük harfe çevirir (I→ı, İ→i), noktalama ve fazla boşlukları atar."""
    text = unicodedata.normalize("NFC", text).replace("I", "ı").replace("İ", "i").lower()
    text = text.replace("i̇", "i")  # birleşik nokta kalıntısı
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def _edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        current = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            current[j] = min(
                previous[j] + 1,  # silme
                current[j - 1] + 1,  # ekleme
                previous[j - 1] + (r != h),  # değiştirme
            )
        previous = current
    return previous[-1]


@dataclass(frozen=True)
class WERResult:
    errors: int
    reference_words: int

    @property
    def wer(self) -> float:
        return self.errors / self.reference_words if self.reference_words else 0.0


def word_errors(reference: str, hypothesis: str) -> WERResult:
    ref, hyp = normalize_tr(reference).split(), normalize_tr(hypothesis).split()
    return WERResult(errors=_edit_distance(ref, hyp), reference_words=len(ref))


def corpus_wer(pairs: Sequence[tuple[str, str]]) -> float:
    """Derlem düzeyinde WER: toplam hata / toplam referans kelime."""
    results = [word_errors(r, h) for r, h in pairs]
    total = sum(r.reference_words for r in results)
    return sum(r.errors for r in results) / total if total else 0.0
