from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
import gzip
from pathlib import Path
import uuid

import pytest
import requests

from conftest import BASE
from app.models.models import (
    User,
    OpeningSubmission,
    StockEntry,
    JournalLine,
    LedgerEntry,
    UserNotification,
    AutomationSetting,
    AutomationJob,
)
from app.services.automation_service import (
    AutomationSettings,
    AutomationRunner,
    BackupRunner,
    claim,
    enqueue,
    deliver,
    IST,
)
from app.core.config import settings


def opening(product=1, **extras):
    return {
        "submission_id": uuid.uuid4().hex,
        "financial_year": "2026-27",
        "opening_date": "2026-04-01",
        "stock_items": [
            {
                "product_id": product,
                "warehouse_id": 1,
                "quantity": "2.500",
                "unit_cost": "100.12",
                "opening_date": "2026-04-01",
            }
        ],
        **extras,
    }


@pytest.mark.parametrize(
    "role,route,status",
    [
        ("sales", "/settings/users-permissions", 403),
        ("admin", "/settings/users-permissions", 403),
        ("accountant", "/reports/pnl", 403),
        ("admin", "/reports/pnl", 403),
        ("warehouse", "/journal/", 403),
        ("sales", "/bank-reconciliation/", 403),
        ("super_admin", "/settings/users-permissions", 200),
        ("accountant", "/journal/", 200),
    ],
)
def test_existing_role_guards(headers, role, route, status):
    assert (
        requests.get(BASE + route, headers=headers[role], timeout=15).status_code
        == status
    )


def test_warehouse_survives_login_reload(headers):
    response = requests.get(BASE + "/auth/me", headers=headers["warehouse"], timeout=15)
    assert response.json()["warehouse_id"] == 1


def test_saved_permissions_enforced_and_shared_lookups(headers, db):
    user = db.query(User).filter_by(username="repair_sales").one()
    try:
        assert (
            requests.put(
                BASE + f"/settings/users-permissions/{user.id}",
                headers=headers["super_admin"],
                json={"page_permissions": ["billing"]},
                timeout=15,
            ).status_code
            == 200
        )
        assert (
            requests.get(
                BASE + "/reports/sales?date_from=2026-04-01&date_to=2026-04-02",
                headers=headers["sales"],
                timeout=15,
            ).status_code
            == 403
        )
        assert (
            requests.get(
                BASE + "/products/", headers=headers["sales"], timeout=15
            ).status_code
            == 200
        )
        assert (
            requests.get(
                BASE + "/customers/", headers=headers["sales"], timeout=15
            ).status_code
            == 200
        )
        assert (
            requests.put(
                BASE + f"/settings/users-permissions/{user.id}",
                headers=headers["super_admin"],
                json={"page_permissions": ["invented_page"]},
                timeout=15,
            ).status_code
            == 422
        )
        requests.put(
            BASE + f"/settings/users-permissions/{user.id}",
            headers=headers["super_admin"],
            json={"page_permissions": []},
            timeout=15,
        )
        assert (
            requests.get(
                BASE + "/invoices/", headers=headers["sales"], timeout=15
            ).status_code
            == 403
        )
    finally:
        requests.put(
            BASE + f"/settings/users-permissions/{user.id}",
            headers=headers["super_admin"],
            json={"page_permissions": None},
            timeout=15,
        )


def test_opening_posts_balanced_fifo_party_and_cash(headers, db):
    data = opening(
        1,
        customer_balances=[
            {"customer_id": 1, "opening_balance": "80.25", "opening_date": "2026-04-01"}
        ],
        vendor_balances=[
            {"vendor_id": 1, "opening_balance": "35.10", "opening_date": "2026-04-01"}
        ],
        cash_balance={"amount": "50.00", "opening_date": "2026-04-01"},
        bank_balances=[
            {
                "account_code": "RPR_BANK",
                "bank_name": "Repair bank",
                "account_number": "TEST1",
                "amount": "15.00",
                "opening_date": "2026-04-01",
            }
        ],
        other_assets="10.00",
        other_liabilities="5.00",
    )
    response = requests.post(
        BASE + "/opening-balances/",
        json=data,
        headers=headers["super_admin"],
        timeout=15,
    )
    assert response.status_code == 201, response.text
    cash = requests.get(
        BASE + "/cash-closing/today?closing_date=2026-04-01",
        headers=headers["accountant"],
        timeout=15,
    )
    assert cash.status_code == 200, cash.text
    assert Decimal(str(cash.json()["opening_balance"])) == Decimal("50.00")
    journal_id = response.json()["journal_entry_id"]
    lines = db.query(JournalLine).filter_by(journal_entry_id=journal_id).all()
    debit = sum(line.amount for line in lines if line.transaction_type == "debit")
    credit = sum(line.amount for line in lines if line.transaction_type == "credit")
    assert debit == credit == Decimal("405.55")
    stock = (
        db.query(StockEntry)
        .filter_by(reference_type="opening_balance", reference_id=journal_id)
        .one()
    )
    assert stock.remaining_qty == Decimal("2.500") and stock.unit_cost == Decimal(
        "100.12"
    )
    assert str(stock.entry_date) == "2026-04-01"
    assert (
        db.query(LedgerEntry)
        .filter_by(reference_id=journal_id, reference_type="opening_balance")
        .count()
        == 2
    )
    repeated = requests.post(
        BASE + "/opening-balances/",
        json=data,
        headers=headers["super_admin"],
        timeout=15,
    )
    assert repeated.json() == response.json()
    data["submission_id"] = uuid.uuid4().hex
    assert (
        requests.post(
            BASE + "/opening-balances/",
            json=data,
            headers=headers["super_admin"],
            timeout=15,
        ).status_code
        == 409
    )


def test_opening_invalid_party_is_atomic(headers, db):
    data = opening(
        2,
        customer_balances=[
            {"customer_id": 999999, "opening_balance": 1, "opening_date": "2026-04-01"}
        ],
    )
    response = requests.post(
        BASE + "/opening-balances/",
        json=data,
        headers=headers["super_admin"],
        timeout=15,
    )
    assert response.status_code == 422
    assert db.query(StockEntry).filter_by(product_id=2).count() == 0
    assert db.get(OpeningSubmission, data["submission_id"]) is None


@pytest.mark.parametrize("role", ["sales", "warehouse", "accountant", "admin"])
def test_opening_stays_super_admin_only(headers, role):
    assert (
        requests.post(
            BASE + "/opening-balances/",
            json=opening(2),
            headers=headers[role],
            timeout=15,
        ).status_code
        == 403
    )


def test_opening_concurrent_retry_does_not_duplicate(headers, db):
    data = opening(3)
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: requests.post(
                    BASE + "/opening-balances/",
                    json=data,
                    headers=headers["super_admin"],
                    timeout=30,
                ),
                range(2),
            )
        )
    assert all(r.status_code == 201 for r in results), [r.text for r in results]
    assert results[0].json() == results[1].json()
    assert db.query(StockEntry).filter_by(product_id=3).count() == 1


def test_csv_invalid_row_does_not_partially_post(headers, db):
    csv = "part_code,warehouse_name,quantity,unit_cost\nREPAIR4,Repair Main,2,10\nMISSING,Repair Main,1,10\n"
    result = requests.post(
        BASE + "/opening-balances/stock/bulk-upload?opening_date=2026-04-01",
        files={"file": ("stock.csv", csv, "text/csv")},
        headers=headers["super_admin"],
        timeout=15,
    )
    assert result.status_code == 200, result.text
    assert result.json()["success_count"] == 0 and result.json()["error_count"] == 1
    assert db.query(StockEntry).filter_by(product_id=4).count() == 0
    csv = "part_code,warehouse_name,quantity,unit_cost\nREPAIR4,Repair Main,2,10\n"
    for _ in range(2):
        result = requests.post(
            BASE + "/opening-balances/stock/bulk-upload?opening_date=2026-04-01",
            files={"file": ("stock.csv", csv, "text/csv")},
            headers=headers["super_admin"],
            timeout=15,
        )
        assert result.status_code == 200, result.text
        assert result.json()["success_count"] == 1, result.text
    db.rollback()
    assert db.query(StockEntry).filter_by(product_id=4).count() == 1


def test_settings_persist_redact_and_reject_external_recipients(headers, db):
    response = requests.put(
        BASE + "/notifications/settings",
        headers=headers["super_admin"],
        json={
            "smtp_password": "Synthetic-test-password",
            "notify_low_stock": False,
            "admin_email": "repair_admin@example.test",
        },
        timeout=15,
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["smtp_password"] == ""
        and response.json()["smtp_password_configured"] is True
    )
    assert (
        "Synthetic-test-password"
        not in db.get(AutomationSetting, "notifications").value_json
    )
    requests.put(
        BASE + "/notifications/settings",
        headers=headers["super_admin"],
        json={"notify_overdue": False, "smtp_password": ""},
        timeout=15,
    )
    response = requests.get(
        BASE + "/notifications/settings", headers=headers["super_admin"], timeout=15
    )
    assert response.json()["notify_low_stock"] is False
    assert response.json()["smtp_password_configured"] is True
    for route, payload in (
        ("/notifications/settings", {"admin_email": "external@example.test"}),
        (
            "/scheduled-reports/settings",
            {"recipient_emails": ["external@example.test"]},
        ),
    ):
        assert (
            requests.put(
                BASE + route, json=payload, headers=headers["super_admin"], timeout=15
            ).status_code
            == 422
        )


def test_bad_report_time_rejected(headers):
    assert (
        requests.put(
            BASE + "/scheduled-reports/settings",
            json={"daily_sales_time": "99:99"},
            headers=headers["super_admin"],
            timeout=15,
        ).status_code
        == 422
    )


def test_inbox_ownership_and_profit_access(headers, db):
    super_user = db.query(User).filter_by(username="superadmin").one()
    admin = db.query(User).filter_by(username="repair_admin").one()
    enqueue(
        db,
        "report:monthly_pnl:test",
        "reports",
        "Private P&L",
        "Synthetic report",
        super_only=True,
    )
    db.commit()
    private = (
        db.query(UserNotification)
        .filter_by(event_key="report:monthly_pnl:test", user_id=super_user.id)
        .one()
    )
    assert (
        not db.query(UserNotification)
        .filter_by(event_key="report:monthly_pnl:test", user_id=admin.id)
        .first()
    )
    assert (
        requests.patch(
            BASE + f"/notifications/{private.id}/read",
            headers=headers["admin"],
            timeout=15,
        ).status_code
        == 404
    )
    assert (
        requests.patch(
            BASE + f"/notifications/{private.id}/read",
            headers=headers["super_admin"],
            timeout=15,
        ).json()["is_read"]
        is True
    )


def test_job_claim_multiworker_once(db):
    key = "repair-claim-" + uuid.uuid4().hex
    from app.db.session import SessionLocal

    def attempt(_):
        with SessionLocal() as session:
            return claim(session, key)

    with ThreadPoolExecutor(3) as pool:
        assert sum(pool.map(attempt, range(3))) == 1


def test_scheduler_restart_and_reports(db):
    from app.schemas.bank import ScheduledReportSettings

    AutomationSettings.update(
        db,
        "reports",
        ScheduledReportSettings(
            recipient_emails=[
                "repair_admin@example.test",
                "superadmin@vigneshgrowthlab.com",
            ]
        ),
    )
    stamp = datetime(2026, 10, 1, 9, 0, tzinfo=IST)
    AutomationRunner.tick(stamp)
    AutomationRunner.tick(stamp)
    db.rollback()
    jobs = (
        db.query(AutomationJob)
        .filter(AutomationJob.key.like("report:%:2026-10%"))
        .all()
    )
    assert len(jobs) == 4
    assert all(j.status == "success" for j in jobs), [
        (j.key, j.last_error) for j in jobs
    ]
    assert all(j.attempts == 1 for j in jobs)
    assert (
        db.query(UserNotification)
        .filter_by(event_key="report:monthly_pnl:2026-10")
        .count()
        == 1
    )


def test_email_off_reports_configuration_required(headers):
    response = requests.post(
        BASE + "/notifications/test-email",
        json={"to_email": "repair_admin@example.test"},
        headers=headers["super_admin"],
        timeout=15,
    )
    assert response.status_code == 503


def test_backup_disabled_and_admin_cannot_run(headers):
    assert (
        requests.post(
            BASE + "/backup/run", headers=headers["admin"], timeout=15
        ).status_code
        == 403
    )
    assert (
        requests.post(
            BASE + "/backup/run", headers=headers["super_admin"], timeout=15
        ).status_code
        == 503
    )


def test_actual_backup_and_restore(tmp_path, monkeypatch):
    import pymysql
    import subprocess

    monkeypatch.setattr(settings, "BACKUP_ENABLED", True)
    monkeypatch.setattr(settings, "BACKUP_DIR", str(tmp_path))
    dump = Path("C:/Program Files/MariaDB 12.3/bin/mariadb-dump.exe")
    monkeypatch.setattr(settings, "BACKUP_DUMP_EXECUTABLE", str(dump))
    result = BackupRunner.run()
    assert result["status"] == "success"
    with gzip.open(tmp_path / result["filename"], "rb") as source:
        sql = source.read()
    assert b"opening_submissions" in sql and b"CREATE TABLE" in sql
    root = pymysql.connect(host="127.0.0.1", port=3307, user="root", password="")
    with root.cursor() as cursor:
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS wholesale_erp_restore_repair_test"
        )
    root.close()
    command = [
        str(dump.parent / "mariadb.exe"),
        "--host=127.0.0.1",
        "--port=3307",
        "--user=root",
        "wholesale_erp_restore_repair_test",
    ]
    restored = subprocess.run(
        command, input=sql, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
    )
    assert restored.returncode == 0, restored.stderr.decode(errors="replace")[:300]
    connection = pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="",
        database="wholesale_erp_restore_repair_test",
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM opening_submissions")
        assert cursor.fetchone()[0] >= 3
    connection.close()


def test_smtp_failure_is_bounded_and_redacted(db, monkeypatch):
    from app.schemas.bank import NotificationSettingsUpdate
    from app.services import automation_service

    user = db.query(User).filter_by(username="repair_admin").one()
    AutomationSettings.update(
        db,
        "notifications",
        NotificationSettingsUpdate(
            admin_email=user.email, smtp_from_email="erp@example.test"
        ),
    )
    key = "repair:delivery:" + uuid.uuid4().hex
    enqueue(db, key, "accounting", "Synthetic alert", "Test delivery")
    db.commit()
    monkeypatch.setattr(settings, "AUTOMATION_EMAIL_ENABLED", True)

    def fail(*_):
        raise RuntimeError("Do not leak synthetic secret")

    monkeypatch.setattr(automation_service, "send_email", fail)
    for _ in range(3):
        db.query(UserNotification).filter_by(event_key=key).update(
            {"lease_until": None}
        )
        db.commit()
        deliver(db)
    db.expire_all()
    row = db.query(UserNotification).filter_by(event_key=key, user_id=user.id).one()
    assert (
        row.attempts == 3
        and row.email_status == "failed"
        and row.last_error == "RuntimeError"
    )
