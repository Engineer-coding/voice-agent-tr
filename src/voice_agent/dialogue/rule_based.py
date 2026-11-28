"""API anahtarı gerektirmeyen, anahtar kelimeye dayalı basit Türkçe 'LLM'.

Amaç gerçek bir LLM'in yerini tutmak değil; terminal demosunu ve uçtan uca testleri ağsız ve
ücretsiz çalıştırmaktır. Gerçek LLM aynı `LLM` arayüzünü uygular.
"""

import json
import re
from datetime import date
from decimal import Decimal
from typing import Any

from voice_agent.dialogue.models import (
    Intent,
    LLMDecision,
    LLMRequest,
    Message,
    Phase,
    ToolCall,
)
from voice_agent.tools.schemas import FaultCategory, ToolName

MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}  # fmt: skip
MONTH_NAMES = {v: k.capitalize() for k, v in MONTHS.items()}

INTENT_KEYWORDS: list[tuple[Intent, tuple[str, ...]]] = [
    (
        Intent.FAULT_REPORT,
        ("arıza", "modem", "çalışmıyor", "bağlanamıyorum", "kesik", "ışık", "yavaş"),
    ),
    (Intent.PACKAGE_CHANGE, ("paket", "tarife", "daha fazla internet", "gb")),
    (Intent.BILLING, ("fatura", "borç", "ödeme", "ücret")),
]
HANDOFF_KEYWORDS = ("temsilci", "insanla", "operatör", "yetkili")

FAULT_CATEGORIES: list[tuple[FaultCategory, tuple[str, ...]]] = [
    ("modem", ("modem", "ışık")),
    ("hiz", ("yavaş", "hız")),
    ("mobil_sebeke", ("şebeke", "çekmiyor", "sinyal")),
    ("baglanti", ("bağlan", "kesik", "kopuyor", "internet yok")),
]


def _lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def _money(value: Any) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"{amount:.2f}".replace(".", ",") + " TL"


def find_phone(text: str) -> str | None:
    digits = re.sub(r"[\s\-()]", "", text)
    match = re.search(r"(?:\+?90)?(0?5\d{9})", digits)
    if not match:
        return None
    number = match.group(1)
    return number if number.startswith("0") else "0" + number


def find_birth_date(text: str) -> date | None:
    # STT tarihleri "14.05.1990", "14 05 1990" veya "14 Mayıs 1990" biçiminde yazabilir.
    for match in re.finditer(r"\b(\d{1,2})[./\-\s](\d{1,2})[./\-\s](\d{4})\b", text):
        day, month, year = (int(g) for g in match.groups())
        if (found := _valid_date(year, month, day)) is not None:
            return found
    lowered = _lower(text)
    for named in re.finditer(r"\b(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})\b", lowered):
        if named.group(2) in MONTHS:
            day, month, year = int(named.group(1)), MONTHS[named.group(2)], int(named.group(3))
            if (found := _valid_date(year, month, day)) is not None:
                return found
    return None


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def format_phone(phone: str) -> str:
    """05321234567 → "0532 123 45 67" (TTS'in grup grup okuması için)."""
    return f"{phone[:4]} {phone[4:7]} {phone[7:9]} {phone[9:]}"


def format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month]} {value.year}"


def detect_intent(text: str) -> Intent | None:
    lowered = _lower(text)
    for intent, words in INTENT_KEYWORDS:
        if any(w in lowered for w in words):
            return intent
    return None


def _last(request: LLMRequest) -> Message | None:
    return request.messages[-1] if request.messages else None


def _last_tool_data(request: LLMRequest, name: ToolName) -> dict[str, Any] | None:
    for message in reversed(request.messages):
        if message.role == "tool" and message.tool_name == name and not message.is_error:
            data: dict[str, Any] = json.loads(message.content)
            return data
    return None


def _identity_texts(messages: list[Message]) -> list[str]:
    """Son doğrulama denemesinden bu yana müşterinin söyledikleri (eskiden yeniye)."""
    texts: list[str] = []
    for message in reversed(messages):
        if message.role == "tool" and message.tool_name == ToolName.VERIFY_IDENTITY:
            break
        if message.role == "user":
            texts.insert(0, message.content)
    return texts


def _heard_identity(texts: list[str]) -> tuple[str | None, date | None]:
    phone = next((p for t in reversed(texts) if (p := find_phone(t))), None)
    birth = next((b for t in reversed(texts) if (b := find_birth_date(t))), None)
    return phone, birth


class RuleBasedLLM:
    """Kural tabanlı Türkçe diyalog politikası."""

    def decide(self, request: LLMRequest) -> LLMDecision:
        last = _last(request)
        if last is not None and last.role == "tool":
            return LLMDecision(reply=self._verbalize(last, request))
        user_text = last.content if last is not None and last.role == "user" else ""
        lowered = _lower(user_text)

        if any(w in lowered for w in HANDOFF_KEYWORDS) and request.phase != Phase.HANDOFF:
            return _call(ToolName.TRANSFER_TO_AGENT, reason="Müşteri temsilci istedi")

        if request.phase == Phase.AUTHENTICATION:
            return self._authenticate(request)

        if request.authenticated:
            intent = detect_intent(user_text)
            current = {
                Phase.BILLING: Intent.BILLING,
                Phase.PACKAGE_CHANGE: Intent.PACKAGE_CHANGE,
                Phase.FAULT_REPORT: Intent.FAULT_REPORT,
            }.get(request.phase)
            if intent is not None and intent != current and request.phase != Phase.CONFIRMATION:
                return LLMDecision(intent=intent)

        match request.phase:
            case Phase.BILLING:
                return _call(ToolName.GET_BILL)
            case Phase.PACKAGE_CHANGE:
                return self._package(request, lowered)
            case Phase.FAULT_REPORT:
                return self._fault(user_text)
            case Phase.CONFIRMATION:
                return LLMDecision(
                    reply="Değişikliği onaylıyor musunuz? Lütfen evet ya da hayır deyin."
                )
            case _:
                return LLMDecision(
                    reply="Fatura, paket değişikliği veya arıza kaydı konusunda yardımcı olabilirim."
                )

    def _authenticate(self, request: LLMRequest) -> LLMDecision:
        # Son doğrulama denemesinden bu yana müşterinin söylediklerini birlikte değerlendir:
        # numara ve doğum tarihi ayrı turlarda verilebilir.
        phone, birth = _heard_identity(_identity_texts(request.messages))
        if phone and birth:
            return _call(ToolName.VERIFY_IDENTITY, phone=phone, birth_date=birth.isoformat())
        if phone:
            return LLMDecision(reply="Teşekkürler. Doğum tarihinizi de söyler misiniz?")
        return LLMDecision(
            reply="Kimliğinizi doğrulamak için telefon numaranızı ve doğum tarihinizi söyler misiniz?"
        )

    def _package(self, request: LLMRequest, lowered: str) -> LLMDecision:
        listing = _last_tool_data(request, ToolName.LIST_PACKAGES)
        if listing is None:
            return _call(ToolName.LIST_PACKAGES)
        packages: list[dict[str, Any]] = listing["packages"]
        size = re.search(r"(\d+)\s*gb", lowered)
        for package in packages:
            by_size = size is not None and int(size.group(1)) == package["data_gb"]
            if by_size or _lower(package["name"]) in lowered:
                return _call(ToolName.SELECT_PACKAGE, package_id=package["id"])
        return LLMDecision(reply="Hangi paketi istersiniz? Örneğin '20 GB olan' diyebilirsiniz.")

    def _fault(self, text: str) -> LLMDecision:
        lowered = _lower(text)
        category: FaultCategory = "diger"
        for name, words in FAULT_CATEGORIES:
            if any(w in lowered for w in words):
                category = name
                break
        generic_request = category == "diger" and re.search(r"arıza\s+(kayd|bildir)", lowered)
        if len(text.strip()) < 3 or generic_request:
            return LLMDecision(reply="Yaşadığınız sorunu biraz anlatır mısınız?")
        return _call(ToolName.CREATE_FAULT_TICKET, category=category, description=text.strip())

    def _verbalize(self, message: Message, request: LLMRequest) -> str:
        data: dict[str, Any] = json.loads(message.content)
        if message.is_error:
            if message.tool_name == ToolName.SELECT_PACKAGE and "zaten" in data.get("detail", ""):
                return "Zaten bu paketi kullanıyorsunuz. Başka bir paket seçmek ister misiniz?"
            return "Üzgünüm, bu işlemi şu anda gerçekleştiremiyorum."
        match message.tool_name:
            case ToolName.VERIFY_IDENTITY:
                if data["verified"]:
                    return (
                        f"Teşekkürler {data['customer_name']}, kimliğiniz doğrulandı. "
                        "Size nasıl yardımcı olabilirim?"
                    )
                if data["remaining_attempts"] <= 0:
                    return "Kimliğinizi doğrulayamadım. Sizi bir müşteri temsilcisine aktarıyorum."
                return _identity_mismatch(request)
            case ToolName.GET_BILL:
                year, month = data["period"].split("-")
                items = sorted(data["items"], key=lambda i: Decimal(i["amount"]), reverse=True)
                text = f"{MONTH_NAMES[int(month)]} {year} faturanız {_money(data['total'])}."
                extras = [i for i in items if "paket ücreti" not in i["description"]]
                if extras:
                    detail = ", ".join(f"{i['description']} {_money(i['amount'])}" for i in extras)
                    text += f" Paket ücretinize ek olarak şu kalemler var: {detail}."
                return text
            case ToolName.LIST_PACKAGES:
                options = "; ".join(
                    f"{p['name']} ({_money(p['monthly_fee'])})"
                    for p in data["packages"]
                    if p["id"] != data["current_package_id"]
                )
                return f"Geçebileceğiniz paketler: {options}. Hangisini istersiniz?"
            case ToolName.SELECT_PACKAGE:
                p = data["selected_package"]
                return (
                    f"{p['name']} paketine geçmek istiyorsunuz, aylık ücreti "
                    f"{_money(p['monthly_fee'])}. Onaylıyor musunuz?"
                )
            case ToolName.CHANGE_PACKAGE:
                return (
                    f"Paketiniz değiştirildi, {data['effective_date']} tarihinden itibaren geçerli. "
                    "Başka bir konuda yardımcı olabilir miyim?"
                )
            case ToolName.CREATE_FAULT_TICKET:
                return (
                    f"Arıza kaydınız {data['id']} numarasıyla açıldı. "
                    "Teknik ekibimiz en kısa sürede sizinle iletişime geçecek."
                )
            case ToolName.TRANSFER_TO_AGENT:
                return "Sizi bir müşteri temsilcisine aktarıyorum, lütfen hatta kalın."
            case _:
                return "İşleminiz tamamlandı."


def _identity_mismatch(request: LLMRequest) -> str:
    """Anlaşılan numara ve tarihi geri okur: hata STT'den mi müşteriden mi, müşteri duyabilsin."""
    # Son mesaj doğrulama sonucudur; ondan önceki denemede söylenenlere bakılır.
    phone, birth = _heard_identity(_identity_texts(request.messages[:-1]))
    heard = ""
    if phone and birth:
        heard = (
            f" Numaranızı {format_phone(phone)}, doğum tarihinizi {format_date(birth)} "
            "olarak anladım."
        )
    return (
        f"Bilgiler eşleşmedi.{heard} Telefon numaranızı ve doğum tarihinizi tekrar söyler "
        "misiniz? İsterseniz ekrandaki alana yazabilirsiniz."
    )


def _call(name: ToolName, **arguments: Any) -> LLMDecision:
    return LLMDecision(tool_call=ToolCall(name=name, arguments=arguments))
