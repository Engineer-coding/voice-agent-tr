"""Sahte CRM HTTP API'si."""

import os
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException

from mock_crm.db import CRMRepository
from mock_crm.models import (
    Bill,
    Customer,
    IdentityRequest,
    IdentityResponse,
    Package,
    PackageChangeRequest,
    PackageChangeResponse,
    Ticket,
    TicketRequest,
)

TICKET_CATEGORIES = {"modem", "baglanti", "hiz", "mobil_sebeke", "diger"}


def create_app(repo: CRMRepository) -> FastAPI:
    app = FastAPI(title="mock-crm")

    def _customer_or_404(customer_id: str) -> Customer:
        customer = repo.get_customer(customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Müşteri bulunamadı")
        return customer

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/identity/verify")
    def verify_identity(request: IdentityRequest) -> IdentityResponse:
        customer = repo.find_customer(request.phone, request.birth_date)
        if customer is None:
            return IdentityResponse(verified=False)
        return IdentityResponse(verified=True, customer_id=customer.id, customer_name=customer.name)

    @app.get("/customers/{customer_id}")
    def get_customer(customer_id: str) -> Customer:
        return _customer_or_404(customer_id)

    @app.get("/customers/{customer_id}/bill")
    def get_bill(customer_id: str, period: str | None = None) -> Bill:
        _customer_or_404(customer_id)
        bill = repo.get_bill(customer_id, period)
        if bill is None:
            raise HTTPException(status_code=404, detail="Fatura bulunamadı")
        return bill

    @app.get("/packages")
    def list_packages() -> list[Package]:
        return repo.list_packages()

    @app.post("/customers/{customer_id}/package")
    def change_package(customer_id: str, request: PackageChangeRequest) -> PackageChangeResponse:
        customer = _customer_or_404(customer_id)
        if repo.get_package(request.package_id) is None:
            raise HTTPException(status_code=422, detail="Geçersiz paket")
        if customer.package_id == request.package_id:
            raise HTTPException(status_code=409, detail="Müşteri zaten bu pakette")
        repo.set_package(customer_id, request.package_id)
        today = date.today()
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        return PackageChangeResponse(
            customer_id=customer_id,
            old_package_id=customer.package_id,
            new_package_id=request.package_id,
            effective_date=next_month,
        )

    @app.get("/customers/{customer_id}/tickets")
    def list_tickets(customer_id: str) -> list[Ticket]:
        _customer_or_404(customer_id)
        return repo.list_tickets(customer_id)

    @app.post("/customers/{customer_id}/tickets", status_code=201)
    def create_ticket(customer_id: str, request: TicketRequest) -> Ticket:
        _customer_or_404(customer_id)
        if request.category not in TICKET_CATEGORIES:
            raise HTTPException(status_code=422, detail="Geçersiz arıza kategorisi")
        return repo.create_ticket(customer_id, request.category, request.description)

    return app


def default_app() -> FastAPI:
    """uvicorn fabrikası: `uvicorn mock_crm.app:default_app --factory`."""
    db_path = Path(os.environ.get("MOCK_CRM_DB", "data/mock_crm.sqlite3"))
    if not db_path.exists():
        from mock_crm.seed import seed

        db_path.parent.mkdir(parents=True, exist_ok=True)
        seed(db_path)
    return create_app(CRMRepository(db_path))
