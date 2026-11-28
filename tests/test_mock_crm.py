from fastapi.testclient import TestClient

from mock_crm.db import CRMRepository
from tests.conftest import DEMO_ID, DEMO_PHONE


def test_identity_verification(crm_http: TestClient) -> None:
    ok = crm_http.post("/identity/verify", json={"phone": DEMO_PHONE, "birth_date": "1990-05-14"})
    assert ok.json() == {"verified": True, "customer_id": DEMO_ID, "customer_name": "Ayşe Yılmaz"}
    bad = crm_http.post("/identity/verify", json={"phone": DEMO_PHONE, "birth_date": "1991-05-14"})
    assert bad.json()["verified"] is False


def test_identity_rejects_malformed_phone(crm_http: TestClient) -> None:
    r = crm_http.post("/identity/verify", json={"phone": "123", "birth_date": "1990-05-14"})
    assert r.status_code == 422


def test_latest_bill_is_current_period_with_roaming(crm_http: TestClient) -> None:
    bill = crm_http.get(f"/customers/{DEMO_ID}/bill").json()
    assert bill["period"] == "2026-11"
    assert any("roaming" in item["description"] for item in bill["items"])


def test_change_package_updates_customer(crm_http: TestClient, crm_repo: CRMRepository) -> None:
    r = crm_http.post(f"/customers/{DEMO_ID}/package", json={"package_id": "P20"})
    assert r.status_code == 200
    customer = crm_repo.get_customer(DEMO_ID)
    assert customer is not None and customer.package_id == "P20"


def test_change_to_same_package_conflicts(crm_http: TestClient) -> None:
    r = crm_http.post(f"/customers/{DEMO_ID}/package", json={"package_id": "P10"})
    assert r.status_code == 409


def test_ticket_creation(crm_http: TestClient) -> None:
    r = crm_http.post(
        f"/customers/{DEMO_ID}/tickets", json={"category": "modem", "description": "Işık yok"}
    )
    assert r.status_code == 201
    assert r.json()["id"].startswith("ARZ-")
