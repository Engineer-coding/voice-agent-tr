"""Sentetik müşteri verisi üretir. Gerçek kişisel veri içermez."""

import random
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

# Testlerde ve demoda kullanılan bilinen müşteri. Tamamen kurgusaldır.
DEMO_CUSTOMER = Customer(id="C0001", name="Ayşe Yılmaz", phone="05321234567", package_id="P10")
DEMO_BIRTH_DATE = date(1990, 5, 14)
DEMO_TC_NO = "10000000146"  # Algoritmaya uygun, kurgusal numara


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


def seed(db_path: Path, customers: int = 50, today: date | None = None, rng_seed: int = 42) -> None:
    """Veritabanını şemayla oluşturur ve sentetik veriyle doldurur."""
    today = today or date.today()
    repo = CRMRepository(db_path)
    repo.create_schema()
    for package in PACKAGES:
        repo.add_package(package)

    fake = Faker("tr_TR")
    Faker.seed(rng_seed)
    rnd = random.Random(rng_seed)
    periods = recent_periods(today)

    repo.add_customer(DEMO_CUSTOMER, DEMO_BIRTH_DATE, DEMO_TC_NO)
    base = PACKAGES[1].monthly_fee
    for period in periods[:-1]:
        repo.add_bill(
            DEMO_CUSTOMER.id, period, [BillItem(description="Orta 10 GB paket ücreti", amount=base)]
        )
    # Bu ayki fatura yurt dışı kullanımı nedeniyle yüksek.
    repo.add_bill(
        DEMO_CUSTOMER.id,
        periods[-1],
        [
            BillItem(description="Orta 10 GB paket ücreti", amount=base),
            BillItem(description="Yurt dışı (roaming) veri kullanımı", amount=Decimal("412.50")),
            BillItem(description="Paket aşımı ek internet 2 GB", amount=Decimal("59.80")),
        ],
    )

    used_phones = {DEMO_CUSTOMER.phone}
    for n in range(2, customers + 1):
        phone = DEMO_CUSTOMER.phone
        while phone in used_phones:
            phone = "05" + "".join(str(rnd.randint(0, 9)) for _ in range(9))
        used_phones.add(phone)
        package = rnd.choice(PACKAGES)
        customer = Customer(id=f"C{n:04d}", name=fake.name(), phone=phone, package_id=package.id)
        birth = fake.date_of_birth(minimum_age=18, maximum_age=80)
        repo.add_customer(customer, birth, "1" + "".join(str(rnd.randint(0, 9)) for _ in range(10)))
        for period in periods:
            items = [
                BillItem(description=f"{package.name} paket ücreti", amount=package.monthly_fee)
            ]
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
