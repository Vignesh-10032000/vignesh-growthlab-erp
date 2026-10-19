import os
from pathlib import Path
import sys

import pytest
import requests
from sqlalchemy.engine import make_url

os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://erp_user:erp_password@127.0.0.1:3307/wholesale_erp_repair_test",
)
if not (make_url(os.environ["DATABASE_URL"]).database or "").endswith("_repair_test"):
    raise RuntimeError("Repair tests require an isolated _repair_test database")
os.environ.setdefault("DEBUG", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.db.session import SessionLocal
from app.models.models import User, Warehouse, Category, Product, Customer, Vendor
from app.core.security import hash_password

BASE = "http://127.0.0.1:8001/api/v1"


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    with SessionLocal() as db:
        from app.models.models import EInvoiceLog, Cheque, Purchase, Invoice

        for model in (EInvoiceLog, Cheque, Purchase, Invoice):
            db.query(model).delete()
        db.commit()
        from app.models.models import (
            OpeningEntry,
            OpeningSubmission,
            JournalLine,
            JournalEntry,
            LedgerEntry,
            StockEntry,
            WarehouseStock,
            UserNotification,
            AutomationJob,
            AutomationSetting,
        )

        for model in (
            OpeningEntry,
            OpeningSubmission,
            JournalLine,
            JournalEntry,
            LedgerEntry,
            StockEntry,
            WarehouseStock,
            UserNotification,
            AutomationJob,
            AutomationSetting,
        ):
            db.query(model).delete()
        db.commit()
        if not db.get(Warehouse, 1):
            db.add(
                Warehouse(
                    id=1,
                    name="Repair Main",
                    code="REPAIR",
                    is_active=True,
                    is_default=True,
                )
            )
        if not db.get(Warehouse, 2):
            db.add(Warehouse(id=2, name="Repair Other", code="REPAIR2", is_active=True))
        db.commit()
        for role in ("admin", "accountant", "sales", "warehouse"):
            username = "repair_" + role
            user = db.query(User).filter_by(username=username).first()
            if not user:
                user = User(
                    username=username,
                    full_name="Repair " + role,
                    email=username + "@example.test",
                    role=role,
                    hashed_password=hash_password("RepairPass@123"),
                    is_active=True,
                    warehouse_id=1 if role == "warehouse" else None,
                )
                db.add(user)
            user.page_permissions = None
            user.is_locked = False
        if not db.get(Category, 1):
            db.add(Category(id=1, name="Repair category", prefix="RPR", is_active=True))
        db.commit()
        for i in range(1, 31):
            if not db.get(Product, i):
                db.add(
                    Product(
                        id=i,
                        category_id=1,
                        part_code=f"REPAIR{i}",
                        part_name=f"Repair product {i}",
                        purchase_cost=100,
                        floor_price=110,
                        b2b_price=120,
                        b2c_price=130,
                        mrp=140,
                        hsn_code="854442",
                        gst_percent=18,
                        low_stock_threshold=5,
                        is_active=True,
                    )
                )
        if not db.get(Customer, 1):
            db.add(Customer(id=1, trade_name="Repair customer", is_active=True))
        if not db.get(Vendor, 1):
            db.add(Vendor(id=1, trade_name="Repair vendor", is_active=True))
        db.commit()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture(scope="session")
def headers():
    result = {}
    for role in ("super_admin", "admin", "accountant", "sales", "warehouse"):
        username = "superadmin" if role == "super_admin" else "repair_" + role
        password = "Admin@1234" if role == "super_admin" else "RepairPass@123"
        response = requests.post(
            BASE + "/auth/login",
            json={"username": username, "password": password},
            timeout=15,
        )
        assert response.status_code == 200, response.text
        result[role] = {"Authorization": "Bearer " + response.json()["access_token"]}
    return result
