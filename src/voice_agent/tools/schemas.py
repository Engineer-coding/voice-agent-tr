"""Araçların Pydantic girdi şemaları ve CRM yanıt modelleri.

Kurallar:
- Girdi şemaları `extra="forbid"` kullanır: LLM'in eklediği bilinmeyen alanlar (ör. `customer_id`)
  çağrıyı geçersiz kılar. Müşteri kimliği her zaman oturumdan gelir, asla LLM'den gelmez.
- Doğrulanmamış argümanla hiçbir araç çağrılmaz.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolName(StrEnum):
    VERIFY_IDENTITY = "verify_identity"
    GET_BILL = "get_bill"
    LIST_PACKAGES = "list_packages"
    SELECT_PACKAGE = "select_package"
    CHANGE_PACKAGE = "change_package"
    CREATE_FAULT_TICKET = "create_fault_ticket"
    TRANSFER_TO_AGENT = "transfer_to_agent"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Araç girdileri ---


class VerifyIdentityArgs(StrictModel):
    """Müşterinin telefon numarası ve doğum tarihiyle kimliğini doğrular."""

    phone: str = Field(pattern=r"^05\d{9}$", description="11 haneli cep telefonu, ör. 05321234567")
    birth_date: date


class GetBillArgs(StrictModel):
    """Doğrulanmış müşterinin faturasını getirir. Dönem verilmezse en son fatura."""

    period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-AA")


class ListPackagesArgs(StrictModel):
    """Satıştaki paketleri listeler."""


class SelectPackageArgs(StrictModel):
    """Müşterinin geçmek istediği paketi seçer. Değişiklik yapmaz, onay ister."""

    package_id: str = Field(min_length=1, max_length=20)


class ChangePackageArgs(StrictModel):
    """Paketi değiştirir. Yalnızca sistem çağırabilir, LLM çağıramaz."""

    package_id: str = Field(min_length=1, max_length=20)


FaultCategory = Literal["modem", "baglanti", "hiz", "mobil_sebeke", "diger"]


class CreateFaultTicketArgs(StrictModel):
    """Müşterinin anlattığı arıza için kayıt açar."""

    category: FaultCategory
    description: str = Field(min_length=3, max_length=1000)


class TransferToAgentArgs(StrictModel):
    """Görüşmeyi canlı müşteri temsilcisine devreder."""

    reason: str = Field(min_length=1, max_length=300)


TOOL_ARGS: dict[ToolName, type[StrictModel]] = {
    ToolName.VERIFY_IDENTITY: VerifyIdentityArgs,
    ToolName.GET_BILL: GetBillArgs,
    ToolName.LIST_PACKAGES: ListPackagesArgs,
    ToolName.SELECT_PACKAGE: SelectPackageArgs,
    ToolName.CHANGE_PACKAGE: ChangePackageArgs,
    ToolName.CREATE_FAULT_TICKET: CreateFaultTicketArgs,
    ToolName.TRANSFER_TO_AGENT: TransferToAgentArgs,
}


# --- CRM yanıtları ---


class IdentityResult(BaseModel):
    verified: bool
    customer_id: str | None = None
    customer_name: str | None = None


class BillItem(BaseModel):
    description: str
    amount: Decimal


class Bill(BaseModel):
    customer_id: str
    period: str
    total: Decimal
    items: list[BillItem]


class Package(BaseModel):
    id: str
    name: str
    data_gb: int
    minutes: int
    monthly_fee: Decimal


class Customer(BaseModel):
    id: str
    name: str
    phone: str
    package_id: str


class PackageChange(BaseModel):
    customer_id: str
    old_package_id: str
    new_package_id: str
    effective_date: date


class Ticket(BaseModel):
    id: str
    customer_id: str
    category: str
    description: str
    status: str
    created_at: datetime
