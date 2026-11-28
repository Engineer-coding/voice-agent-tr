"""Müşterinin açık onayını kural tabanlı olarak algılar.

Geri alınamaz işlemler (paket değişikliği) için onay kararı LLM'e bırakılmaz: bir saldırgan
LLM'i "müşteri onayladı" demeye ikna etse bile değişiklik yalnızca müşterinin kendi sözünden
çıkan açık bir "evet" ile yapılır.
"""

import re
from typing import Literal

_NO = re.compile(
    r"\b(hayır|hayir|istemiyorum|vazgeçtim|vazgectim|iptal|onaylamıyorum|onaylamiyorum)\b"
)
_YES = re.compile(r"\b(evet|onaylıyorum|onayliyorum|onaylarım|onaylarim|kabul ediyorum)\b")


def parse_confirmation(text: str) -> Literal["yes", "no"] | None:
    """Açık evet için "yes", açık hayır için "no", belirsizse None döndürür."""
    normalized = text.casefold().replace("İ".casefold(), "i")
    if _NO.search(normalized):
        return "no"
    if _YES.search(normalized):
        return "yes"
    return None
