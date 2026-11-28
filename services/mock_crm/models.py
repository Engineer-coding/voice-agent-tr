"""Sahte CRM'in API modelleri."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

PHONE_PATTERN = r"^05\d{9}$"
PERIOD_PATTERN = r"^\d{4}-\d{2}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Package(StrictModel):
    id: str
    name: str
    data_gb: int
    minutes: int
    monthly_fee: Decimal


class Customer(StrictModel):
    id: str
    name: str
    phone: str
    package_id: str


class BillItem(StrictModel):
    description: str
    amount: Decimal


class Bill(StrictModel):
    customer_id: str
    period: str = Field(pattern=PERIOD_PATTERN)
    total: Decimal
    items: list[BillItem]


class IdentityRequest(StrictModel):
    phone: str = Field(pattern=PHONE_PATTERN)
    birth_date: date


class IdentityResponse(StrictModel):
    verified: bool
    customer_id: str | None = None
    customer_name: str | None = None


class PackageChangeRequest(StrictModel):
    package_id: str


class PackageChangeResponse(StrictModel):
    customer_id: str
    old_package_id: str
    new_package_id: str
    effective_date: date


class TicketRequest(StrictModel):
    category: str
    description: str = Field(min_length=3, max_length=1000)


class Ticket(StrictModel):
    id: str
    customer_id: str
    category: str
    description: str
    status: str
    created_at: datetime
