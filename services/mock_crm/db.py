"""SQLite tabanlı sahte CRM deposu."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from mock_crm.models import Bill, BillItem, Customer, Package, Ticket

SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data_gb INTEGER NOT NULL,
    minutes INTEGER NOT NULL,
    monthly_fee TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    birth_date TEXT NOT NULL,
    tc_no TEXT NOT NULL,
    package_id TEXT NOT NULL REFERENCES packages(id)
);
CREATE TABLE IF NOT EXISTS bills (
    customer_id TEXT NOT NULL REFERENCES customers(id),
    period TEXT NOT NULL,
    items TEXT NOT NULL,
    PRIMARY KEY (customer_id, period)
);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class CRMRepository:
    """Sahte CRM verisine erişim. Her çağrı kendi bağlantısını açar (iş parçacığı güvenli)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # --- yazma (tohumlama) ---

    def add_package(self, package: Package) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO packages VALUES (?, ?, ?, ?, ?)",
                (
                    package.id,
                    package.name,
                    package.data_gb,
                    package.minutes,
                    str(package.monthly_fee),
                ),
            )

    def add_customer(self, customer: Customer, birth_date: date, tc_no: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)",
                (
                    customer.id,
                    customer.name,
                    customer.phone,
                    birth_date.isoformat(),
                    tc_no,
                    customer.package_id,
                ),
            )

    def add_bill(self, customer_id: str, period: str, items: list[BillItem]) -> None:
        payload = json.dumps(
            [{"description": i.description, "amount": str(i.amount)} for i in items]
        )
        with self._connect() as conn:
            conn.execute("INSERT INTO bills VALUES (?, ?, ?)", (customer_id, period, payload))

    # --- okuma ---

    def list_packages(self) -> list[Package]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM packages ORDER BY data_gb").fetchall()
        return [_package(r) for r in rows]

    def get_package(self, package_id: str) -> Package | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        return _package(row) if row else None

    def get_customer(self, customer_id: str) -> Customer | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return _customer(row) if row else None

    def find_customer(self, phone: str, birth_date: date) -> Customer | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE phone = ? AND birth_date = ?",
                (phone, birth_date.isoformat()),
            ).fetchone()
        return _customer(row) if row else None

    def get_bill(self, customer_id: str, period: str | None) -> Bill | None:
        with self._connect() as conn:
            if period is None:
                row = conn.execute(
                    "SELECT * FROM bills WHERE customer_id = ? ORDER BY period DESC LIMIT 1",
                    (customer_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM bills WHERE customer_id = ? AND period = ?",
                    (customer_id, period),
                ).fetchone()
        if row is None:
            return None
        items = [
            BillItem(description=i["description"], amount=Decimal(i["amount"]))
            for i in json.loads(row["items"])
        ]
        return Bill(
            customer_id=row["customer_id"],
            period=row["period"],
            total=sum((i.amount for i in items), Decimal("0")),
            items=items,
        )

    def list_tickets(self, customer_id: str) -> list[Ticket]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE customer_id = ? ORDER BY created_at", (customer_id,)
            ).fetchall()
        return [_ticket(r) for r in rows]

    # --- değiştirme ---

    def set_package(self, customer_id: str, package_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE customers SET package_id = ? WHERE id = ?", (package_id, customer_id)
            )

    def create_ticket(self, customer_id: str, category: str, description: str) -> Ticket:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            ticket = Ticket(
                id=f"ARZ-{count + 1:06d}",
                customer_id=customer_id,
                category=category,
                description=description,
                status="acik",
                created_at=datetime.now(UTC),
            )
            conn.execute(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ticket.id,
                    ticket.customer_id,
                    ticket.category,
                    ticket.description,
                    ticket.status,
                    ticket.created_at.isoformat(),
                ),
            )
        return ticket


def _package(row: sqlite3.Row) -> Package:
    return Package(
        id=row["id"],
        name=row["name"],
        data_gb=row["data_gb"],
        minutes=row["minutes"],
        monthly_fee=Decimal(row["monthly_fee"]),
    )


def _customer(row: sqlite3.Row) -> Customer:
    return Customer(
        id=row["id"], name=row["name"], phone=row["phone"], package_id=row["package_id"]
    )


def _ticket(row: sqlite3.Row) -> Ticket:
    return Ticket(
        id=row["id"],
        customer_id=row["customer_id"],
        category=row["category"],
        description=row["description"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
