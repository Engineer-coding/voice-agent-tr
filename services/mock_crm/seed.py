"""Sentetik müşteri verisi üretir. Gerçek kişisel veri içermez."""

import random
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from faker import Faker

from mock_crm.db import CRMRepository
from mock_crm.models import BillItem, Customer, Package

PACKAGES = [
    Package(id="P05", name="Mini 5 GB", data_gb=5, minutes=500, monthly_fee=Decimal("199.90")),
    Package(id="P10", name="Orta 10 GB", data_gb=10, minutes=1000, monthly_fee=Decimal("279.90")),
    Package(id="P20", name="Süper 20 GB", data_gb=20, minutes=1000, monthly_fee=Decimal("349.90")),
    Package(id="P40", name="Mega 40 GB", data_gb=40, minutes=2000, monthly_fee=Decimal("449.90")),
]
_PACKAGES_BY_ID = {p.id: p for p in PACKAGES}


@dataclass(frozen=True)
class FixedCustomer:
    """Testlerde, değerlendirmede ve demoda kullanılan bilinen, kurgusal müşteri."""

    customer: Customer
    birth_date: date
    tc_no: str
    latest_extras: list[BillItem] = field(default_factory=list)


FIXED_CUSTOMERS = [
    FixedCustomer(
        Customer(id="C0001", name="Ayşe Yılmaz", phone="05321234567", package_id="P10"),
        date(1990, 5, 14),
        "10000000146",
        [
            BillItem(description="Yurt dışı (roaming) veri kullanımı", amount=Decimal("412.50")),
            BillItem(description="Paket aşımı ek internet 2 GB", amount=Decimal("59.80")),
        ],
    ),
    FixedCustomer(
        Customer(id="C0002", name="Mehmet Kaya", phone="05339876543", package_id="P05"),
        date(1985, 11, 2),
        "10000000214",
        [BillItem(description="Paket aşımı ek internet 3 GB", amount=Decimal("89.70"))],
    ),
    FixedCustomer(
        Customer(id="C0003", name="Zeynep Demir", phone="05441112233", package_id="P20"),
        date(1978, 3, 23),
        "10000000382",
    ),
    FixedCustomer(
        Customer(id="C0004", name="Can Öztürk", phone="05552223344", package_id="P40"),
        date(2001, 7, 30),
        "10000000450",
        [BillItem(description="Yurt dışı arama", amount=Decimal("136.40"))],
    ),
    FixedCustomer(
        Customer(id="C0005", name="Elif Şahin", phone="05063334455", package_id="P05"),
        date(1995, 12, 9),
        "10000000528",
        [BillItem(description="Premium SMS servis ücreti", amount=Decimal("49.90"))],
    ),
]

DEMO_CUSTOMER = FIXED_CUSTOMERS[0].customer
DEMO_BIRTH_DATE = FIXED_CUSTOMERS[0].birth_date


def recent_periods(today: date, count: int = 3) -> list[str]:
    """Bugünden geriye doğru son `count` dönemi (YYYY-AA) eskiden yeniye döndürür."""
    periods: list[str] = []
    year, month = today.year, today.month
    for _ in range(count):
        periods.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(periods))


def _fee_item(package_id: str) -> BillItem:
    package = _PACKAGES_BY_ID[package_id]
    return BillItem(description=f"{package.name} paket ücreti", amount=package.monthly_fee)


def seed(db_path: Path, customers: int = 50, today: date | None = None, rng_seed: int = 42) -> None:
    """Veritabanını şemayla oluşturur ve sentetik veriyle doldurur."""
    today = today or date.today()
    repo = CRMRepository(db_path)
    repo.create_schema()
    for package in PACKAGES:
        repo.add_package(package)

    periods = recent_periods(today)
    for fixed in FIXED_CUSTOMERS:
        repo.add_customer(fixed.customer, fixed.birth_date, fixed.tc_no)
        fee = _fee_item(fixed.customer.package_id)
        for period in periods[:-1]:
            repo.add_bill(fixed.customer.id, period, [fee])
        repo.add_bill(fixed.customer.id, periods[-1], [fee, *fixed.latest_extras])

    fake = Faker("tr_TR")
    Faker.seed(rng_seed)
    rnd = random.Random(rng_seed)
    used_phones = {f.customer.phone for f in FIXED_CUSTOMERS}
    for n in range(len(FIXED_CUSTOMERS) + 1, customers + 1):
        phone = next(iter(used_phones))
        while phone in used_phones:
            phone = "05" + "".join(str(rnd.randint(0, 9)) for _ in range(9))
        used_phones.add(phone)
        package = rnd.choice(PACKAGES)
        customer = Customer(id=f"C{n:04d}", name=fake.name(), phone=phone, package_id=package.id)
        birth = fake.date_of_birth(minimum_age=18, maximum_age=80)
        repo.add_customer(customer, birth, "1" + "".join(str(rnd.randint(0, 9)) for _ in range(10)))
        for period in periods:
            items = [_fee_item(package.id)]
            if rnd.random() < 0.3:
                items.append(
                    BillItem(
                        description="Paket aşımı ek internet", amount=Decimal(rnd.randint(20, 120))
                    )
                )
            repo.add_bill(customer.id, period, items)


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/mock_crm.sqlite3")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    seed(target)
    print(f"Sahte CRM veritabanı oluşturuldu: {target}")
