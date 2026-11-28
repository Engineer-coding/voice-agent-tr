"""Sahte CRM için HTTP istemcisi. Yanıtları Pydantic ile doğrular."""

from typing import Any, Protocol

from pydantic import TypeAdapter

from voice_agent.tools.schemas import (
    Bill,
    Customer,
    IdentityResult,
    Package,
    PackageChange,
    Ticket,
)


class CRMError(Exception):
    """CRM bir hata döndürdü."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"CRM hatası {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


_PACKAGES = TypeAdapter(list[Package])


class HTTPResponse(Protocol):
    @property
    def is_error(self) -> bool: ...
    @property
    def status_code(self) -> int: ...
    @property
    def text(self) -> str: ...
    def json(self, **kwargs: Any) -> Any: ...


class HTTPClient(Protocol):
    """httpx.Client ve FastAPI TestClient bu arayüzü karşılar."""

    def get(self, url: str, *, params: Any = None) -> HTTPResponse: ...
    def post(self, url: str, *, json: Any = None) -> HTTPResponse: ...


class CRMClient:
    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    def _check(self, response: HTTPResponse) -> HTTPResponse:
        if response.is_error:
            try:
                detail = str(response.json().get("detail", response.text))
            except ValueError:
                detail = response.text
            raise CRMError(response.status_code, detail)
        return response

    def verify_identity(self, phone: str, birth_date: str) -> IdentityResult:
        r = self._http.post("/identity/verify", json={"phone": phone, "birth_date": birth_date})
        return IdentityResult.model_validate(self._check(r).json())

    def get_customer(self, customer_id: str) -> Customer:
        r = self._http.get(f"/customers/{customer_id}")
        return Customer.model_validate(self._check(r).json())

    def get_bill(self, customer_id: str, period: str | None = None) -> Bill:
        params = {"period": period} if period else None
        r = self._http.get(f"/customers/{customer_id}/bill", params=params)
        return Bill.model_validate(self._check(r).json())

    def list_packages(self) -> list[Package]:
        return _PACKAGES.validate_python(self._check(self._http.get("/packages")).json())

    def change_package(self, customer_id: str, package_id: str) -> PackageChange:
        r = self._http.post(f"/customers/{customer_id}/package", json={"package_id": package_id})
        return PackageChange.model_validate(self._check(r).json())

    def create_ticket(self, customer_id: str, category: str, description: str) -> Ticket:
        r = self._http.post(
            f"/customers/{customer_id}/tickets",
            json={"category": category, "description": description},
        )
        return Ticket.model_validate(self._check(r).json())
