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
    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text)
    if match:
        day, month, year = (int(g) for g in match.groups())
    else:
        lowered = _lower(text)
        named = re.search(r"\b(\d{1,2})\s+([a-zçğıöşü]+)\s+(\d{4})\b", lowered)
        if not named or named.group(2) not in MONTHS:
            return None
        day, month, year = int(named.group(1)), MONTHS[named.group(2)], int(named.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


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


class RuleBasedLLM:
    """Kural tabanlı Türkçe diyalog politikası."""

    def decide(self, request: LLMRequest) -> LLMDecision:
        last = _last(request)
        if last is not None and last.role == "tool":
            return LLMDecision(reply=self._verbalize(last))
        user_text = last.content if last is not None and last.role == "user" else ""
        lowered = _lower(user_text)

        if any(w in lowered for w in HANDOFF_KEYWORDS) and request.phase != Phase.HANDOFF:
            return _call(ToolName.TRANSFER_TO_AGENT, reason="Müşteri temsilci istedi")

        if request.phase == Phase.AUTHENTICATION:
            return self._authenticate(user_text)

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

    def _authenticate(self, text: str) -> LLMDecision:
        phone, birth = find_phone(text), find_birth_date(text)
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
        if len(text.strip()) < 3:
            return LLMDecision(reply="Yaşadığınız sorunu biraz anlatır mısınız?")
        return _call(ToolName.CREATE_FAULT_TICKET, category=category, description=text.strip())

    def _verbalize(self, message: Message) -> str:
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
                return "Bilgiler eşleşmedi. Telefon numaranızı ve doğum tarihinizi tekrar söyler misiniz?"
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


def _call(name: ToolName, **arguments: Any) -> LLMDecision:
    return LLMDecision(tool_call=ToolCall(name=name, arguments=arguments))
