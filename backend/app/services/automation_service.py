"""Durable local scheduling, notification delivery, and database backups."""

import asyncio
import base64
import gzip
import hashlib
import json
import logging
import os
from pathlib import Path
import smtplib
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from app.core.page_access import has_page_access
from app.core.security import _role_str
from app.db.session import SessionLocal, db_url
from app.models.models import (
    AutomationSetting,
    AutomationJob,
    UserNotification,
    User,
    Invoice,
    Purchase,
    Product,
    WarehouseStock,
    Cheque,
    EInvoiceLog,
    ActiveSession,
)

log = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
NOTIFICATION_DEFAULTS = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_from_email": "",
    "admin_email": "",
    "accountant_email": "",
    "notify_overdue": True,
    "notify_low_stock": True,
    "notify_large_invoice": True,
    "large_invoice_threshold": 100000,
    "notify_einvoice_failure": True,
    "notify_cheque_bounce": True,
    "notify_daily_summary": True,
    "notify_unknown_ip": True,
    "notify_vendor_due": True,
    "notify_backup": True,
}
REPORT_DEFAULTS = {
    "daily_sales_enabled": True,
    "daily_sales_time": "08:00",
    "weekly_outstanding_enabled": True,
    "monthly_pnl_enabled": True,
    "monthly_stock_enabled": True,
    "monthly_gst_enabled": True,
    "monthly_bank_statement_reminder": True,
    "recipient_emails": [],
}


def cipher():
    return Fernet(
        base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    )


class AutomationSettings:
    @staticmethod
    def get(db, key, private=False):
        defaults = NOTIFICATION_DEFAULTS if key == "notifications" else REPORT_DEFAULTS
        row = db.get(AutomationSetting, key)
        data = {**defaults, **(json.loads(row.value_json) if row else {})}
        encrypted = data.pop("smtp_password_encrypted", "")
        if key == "notifications":
            data["smtp_password_configured"] = bool(encrypted)
            data["email_delivery_enabled"] = settings.AUTOMATION_EMAIL_ENABLED
            if private:
                try:
                    data["smtp_password"] = (
                        cipher().decrypt(encrypted.encode()).decode()
                        if encrypted
                        else ""
                    )
                except InvalidToken:
                    raise HTTPException(
                        503,
                        "SMTP credentials require reconfiguration after a secret-key change",
                    )
            else:
                data["smtp_password"] = ""
        return data

    @staticmethod
    def update(db, key, payload):
        values = payload.model_dump(exclude_unset=True, mode="json")
        row = db.get(AutomationSetting, key)
        stored = json.loads(row.value_json) if row else {}
        for field in ("admin_email", "accountant_email"):
            if values.get(field):
                AutomationSettings.validate_recipients(db, [values[field]])
        if "recipient_emails" in values:
            AutomationSettings.validate_recipients(db, values["recipient_emails"])
        password = values.pop("smtp_password", None)
        if password:
            stored["smtp_password_encrypted"] = (
                cipher().encrypt(password.encode()).decode()
            )
        stored.update({k: v for k, v in values.items() if v is not None})
        if not row:
            row = AutomationSetting(key=key, value_json="{}")
            db.add(row)
        row.value_json = json.dumps(stored)
        db.commit()
        return AutomationSettings.get(db, key)

    @staticmethod
    def validate_recipients(db, emails):
        for email in emails:
            if (
                not db.query(User.id)
                .filter(
                    func.lower(User.email) == email.lower(), User.is_active.is_(True)
                )
                .first()
            ):
                raise HTTPException(422, "Recipients must be active ERP users")

    @staticmethod
    def import_legacy(db):
        for key, filename in (
            ("notifications", "erp_notifications.json"),
            ("reports", "erp_scheduled_reports.json"),
        ):
            if db.get(AutomationSetting, key):
                continue
            path = Path("/tmp") / filename
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            allowed = (
                NOTIFICATION_DEFAULTS if key == "notifications" else REPORT_DEFAULTS
            )
            data = {k: v for k, v in raw.items() if k in allowed}
            if raw.get("smtp_password"):
                data["smtp_password_encrypted"] = (
                    cipher().encrypt(raw["smtp_password"].encode()).decode()
                )
            db.add(AutomationSetting(key=key, value_json=json.dumps(data)))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def eligible(user, page, super_only=False, warehouse_id=None):
    role = _role_str(user)
    roles = {
        "accounting": {"super_admin", "admin", "accountant"},
        "bank": {"super_admin", "admin", "accountant"},
        "reports": {"super_admin", "admin", "accountant"},
        "gst": {"super_admin", "admin", "accountant"},
        "warehouse": {"super_admin", "admin", "warehouse"},
        "purchase": {"super_admin", "admin", "accountant"},
        "security": {"super_admin"},
    }
    if not user.is_active or (super_only and role != "super_admin"):
        return False
    if role not in roles.get(page, {"super_admin", "admin", "accountant"}):
        return False
    if role != "super_admin" and page in {
        "reports",
        "accounting",
        "bank",
        "gst",
        "purchase",
    }:
        if user.warehouse_id or user.admin_warehouses:
            return False
    if warehouse_id and role != "super_admin":
        assigned = user.warehouse_id
        if role == "admin" and user.admin_warehouses:
            if warehouse_id not in {w.warehouse_id for w in user.admin_warehouses}:
                return False
        elif assigned and assigned != warehouse_id:
            return False
    return has_page_access(user, page)


def enqueue(
    db,
    event_key,
    page,
    subject,
    body,
    super_only=False,
    recipients=None,
    warehouse_id=None,
):
    selected = {e.lower() for e in recipients} if recipients is not None else None
    for user in db.query(User).filter(User.is_active.is_(True)).all():
        if not eligible(user, page, super_only, warehouse_id) or (
            selected is not None and user.email.lower() not in selected
        ):
            continue
        if (
            db.query(UserNotification.id)
            .filter_by(event_key=event_key, user_id=user.id)
            .first()
        ):
            continue
        try:
            with db.begin_nested():
                db.add(
                    UserNotification(
                        event_key=event_key,
                        user_id=user.id,
                        page_key=page,
                        subject=subject,
                        warehouse_id=warehouse_id,
                        body=body,
                        email_status="pending",
                    )
                )
                db.flush()
        except IntegrityError:
            pass


def send_email(db, user, subject, body):
    cfg = AutomationSettings.get(db, "notifications", private=True)
    if (
        not settings.AUTOMATION_EMAIL_ENABLED
        or not cfg["smtp_from_email"]
        or not cfg["smtp_host"]
    ):
        raise HTTPException(
            503,
            "Email delivery requires SMTP configuration and AUTOMATION_EMAIL_ENABLED=true",
        )
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, cfg["smtp_from_email"], user.email
    msg.set_content(body)
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=15) as smtp:
        if settings.AUTOMATION_SMTP_TLS:
            smtp.starttls()
        if cfg["smtp_username"]:
            smtp.login(cfg["smtp_username"], cfg["smtp_password"])
        smtp.send_message(msg)


def deliver(db):
    now = datetime.utcnow()
    rows = (
        db.query(UserNotification)
        .filter(
            UserNotification.email_status.in_(
                ["pending", "retry", "configuration_required", "sending"]
            ),
            UserNotification.attempts < 3,
            (UserNotification.lease_until.is_(None))
            | (UserNotification.lease_until < now),
        )
        .order_by(UserNotification.id)
        .limit(50)
        .all()
    )
    cfg = AutomationSettings.get(db, "notifications")
    report_cfg = AutomationSettings.get(db, "reports")
    for row in rows:
        user = db.get(User, row.user_id)
        if not user or not eligible(
            user,
            row.page_key,
            row.event_key.startswith("report:monthly_pnl"),
            row.warehouse_id,
        ):
            row.email_status = "cancelled"
            continue
        configured = (
            report_cfg["recipient_emails"]
            if row.event_key.startswith("report:")
            else [cfg["admin_email"], cfg["accountant_email"]]
        )
        if user.email.lower() not in {e.lower() for e in configured if e}:
            row.email_status = "not_requested"
            continue
        if not settings.AUTOMATION_EMAIL_ENABLED:
            row.email_status = "configuration_required"
            continue
        updated = (
            db.query(UserNotification)
            .filter(
                UserNotification.id == row.id,
                (UserNotification.lease_until.is_(None))
                | (UserNotification.lease_until < now),
            )
            .update(
                {"lease_until": now + timedelta(minutes=2), "email_status": "sending"},
                synchronize_session=False,
            )
        )
        db.commit()
        if not updated:
            continue
        db.refresh(row)
        try:
            send_email(db, user, row.subject, row.body)
            row.email_status, row.last_error = "sent", None
        except HTTPException:
            row.email_status, row.last_error = (
                "configuration_required",
                "SMTP configuration is incomplete",
            )
        except Exception as exc:
            row.attempts += 1
            row.email_status = "failed" if row.attempts >= 3 else "retry"
            row.last_error = type(exc).__name__
        row.lease_until = datetime.utcnow() + timedelta(minutes=2**row.attempts)
        db.commit()
    db.commit()


def claim(db, key):
    for attempt in range(4):
        try:
            return _claim(db, key)
        except OperationalError as exc:
            db.rollback()
            code = getattr(exc.orig, "args", (None,))[0]
            if code not in (1020, 1205, 1213) or attempt == 3:
                raise
            time.sleep(0.05 * (2**attempt))


def _claim(db, key):
    now = datetime.utcnow()
    try:
        with db.begin_nested():
            if not db.get(AutomationJob, key):
                db.add(AutomationJob(key=key, status="pending", attempts=0))
                db.flush()
    except IntegrityError:
        pass
    updated = (
        db.query(AutomationJob)
        .filter(
            AutomationJob.key == key,
            AutomationJob.status != "success",
            AutomationJob.attempts < 3,
            (AutomationJob.lease_until.is_(None)) | (AutomationJob.lease_until < now),
        )
        .update(
            {
                "status": "running",
                "lease_until": now + timedelta(minutes=10),
                "attempts": AutomationJob.attempts + 1,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return bool(updated)


class BackupRunner:
    @staticmethod
    def run_manual():
        key = "backup:manual:" + datetime.now(IST).strftime("%Y%m%d%H%M%S%f")
        with SessionLocal() as db:
            claim(db, key)
            job = db.get(AutomationJob, key)
            try:
                result = BackupRunner.run()
                job.status = "success"
                return result
            except Exception as exc:
                job.status, job.last_error = "failed", type(exc).__name__
                if isinstance(exc, HTTPException):
                    raise
                raise HTTPException(
                    503,
                    "Backup failed; check storage, database privileges, and dump utility",
                )
            finally:
                job.completed_at = datetime.utcnow()
                db.commit()

    @staticmethod
    def run():
        if not settings.BACKUP_ENABLED:
            raise HTTPException(
                503, "Backups require BACKUP_ENABLED=true and a persistent BACKUP_DIR"
            )
        folder = Path(settings.BACKUP_DIR).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (
            datetime.now(IST).strftime("backup_%Y%m%d_%H%M%S_%f") + ".sql.gz"
        )
        partial = target.with_suffix(target.suffix + ".partial")
        url = make_url(db_url)
        config_file = None
        try:
            # Credentials travel in a private temporary option file, never the command line.
            def escape(value):
                return (
                    '"'
                    + str(value or "")
                    .replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    + '"'
                )

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".cnf", delete=False, encoding="utf-8"
            ) as cfg:
                config_file = cfg.name
                cfg.write(
                    "[client]\n"
                    + "\n".join(
                        f"{k}={escape(v)}"
                        for k, v in {
                            "host": url.host,
                            "port": url.port or 3306,
                            "user": url.username,
                            "password": url.password,
                        }.items()
                    )
                )
            os.chmod(config_file, 0o600)
            command = [
                settings.BACKUP_DUMP_EXECUTABLE,
                f"--defaults-extra-file={config_file}",
                "--single-transaction",
                "--routines",
                "--triggers",
                url.database,
            ]
            with tempfile.TemporaryFile() as raw:
                completed = subprocess.run(
                    command,
                    stdout=raw,
                    stderr=subprocess.PIPE,
                    timeout=settings.BACKUP_TIMEOUT_SECONDS,
                    check=False,
                )
                if completed.returncode:
                    raise RuntimeError(
                        "Database dump failed; check database privileges and dump utility"
                    )
                if raw.tell() == 0:
                    raise RuntimeError("Database dump was empty")
                raw.seek(0)
                import shutil

                with gzip.open(partial, "wb") as compressed:
                    shutil.copyfileobj(raw, compressed)
            os.replace(partial, target)
            os.chmod(target, 0o600)
            cutoff = datetime.now().timestamp() - settings.BACKUP_RETENTION_DAYS * 86400
            for old in folder.glob("backup_*.sql.gz"):
                if old != target and old.stat().st_mtime < cutoff:
                    old.unlink()
            return {
                "filename": target.name,
                "status": "success",
                "size_mb": round(target.stat().st_size / 1048576, 4),
            }
        finally:
            if config_file:
                Path(config_file).unlink(missing_ok=True)
            partial.unlink(missing_ok=True)

    @staticmethod
    def status():
        folder = Path(settings.BACKUP_DIR).resolve()
        files = (
            sorted(
                folder.glob("backup_*.sql.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if folder.is_dir()
            else []
        )
        cutoff = datetime.now().timestamp() - 30 * 86400
        backups = [
            {
                "filename": p.name,
                "size_mb": round(p.stat().st_size / 1048576, 4),
                "created_at": datetime.fromtimestamp(
                    p.stat().st_mtime, IST
                ).isoformat(),
                "status": "success",
            }
            for p in files[:30]
        ]
        last = backups[0] if backups else {}
        return {
            "last_backup_time": last.get("created_at"),
            "last_backup_status": "success" if last else "no_backups_found",
            "last_backup_size_mb": last.get("size_mb"),
            "backup_count_last_30_days": sum(
                p.stat().st_mtime >= cutoff for p in files
            ),
            "backups": backups,
            "enabled": settings.BACKUP_ENABLED,
            "note": "Daily at 02:00 Asia/Kolkata; backups require configured persistent storage and dump utility.",
        }


class AutomationRunner:
    @staticmethod
    def report(db, name, now):
        from app.services.reports_service import (
            SalesReportService,
            PnLService,
            StockReportService,
        )
        from app.services.gst_service import GSTR3BService
        from app.utils.helpers import get_financial_year

        today = now.date()
        previous = today.replace(day=1) - timedelta(days=1)
        if name == "daily_sales":
            return SalesReportService.generate(
                db, today - timedelta(days=1), today - timedelta(days=1)
            )
        if name == "weekly_outstanding":
            return {
                "invoices": [
                    {
                        "number": i.invoice_number,
                        "outstanding": str(i.outstanding_amount),
                    }
                    for i in db.query(Invoice)
                    .filter(
                        Invoice.outstanding_amount > 0,
                        Invoice.is_cancelled.is_(False),
                        Invoice.document_type.in_(["b2b_invoice", "b2c_invoice"]),
                    )
                    .all()
                ]
            }
        if name == "monthly_pnl":
            return PnLService.generate(
                db, date_from=previous.replace(day=1), date_to=previous
            )
        if name == "monthly_stock":
            return StockReportService.generate(db)
        if name == "monthly_gst":
            return GSTR3BService.generate(
                db, previous.strftime("%m-%Y"), get_financial_year(previous)
            )
        return {"reminder": "Prepare the monthly bank stock statement."}

    @staticmethod
    def tick(now=None):
        now = now or datetime.now(IST)
        with SessionLocal() as db:
            cfg = AutomationSettings.get(db, "reports")
            notification_cfg = AutomationSettings.get(db, "notifications")
            due = []
            if now.strftime("%H:%M") >= cfg["daily_sales_time"]:
                due.append(("daily_sales", now.date().isoformat()))
                due.append(
                    (
                        "weekly_outstanding",
                        (now.date() - timedelta(days=now.weekday())).isoformat(),
                    )
                )
                due.extend(
                    (name, now.strftime("%Y-%m"))
                    for name in ("monthly_pnl", "monthly_stock", "monthly_gst")
                )
                if now.day >= 25:
                    due.append(
                        ("monthly_bank_statement_reminder", now.strftime("%Y-%m"))
                    )
            for name, period in due:
                enabled = cfg.get(name + "_enabled", cfg.get(name, False))
                if name == "daily_sales":
                    enabled = enabled or notification_cfg["notify_daily_summary"]
                if not enabled:
                    continue
                key = f"report:{name}:{period}"
                if not claim(db, key):
                    continue
                job = db.get(AutomationJob, key)
                try:
                    body = json.dumps(
                        AutomationRunner.report(db, name, now), default=str, indent=2
                    )
                    page = (
                        "gst"
                        if name == "monthly_gst"
                        else "bank"
                        if name.startswith("monthly_bank")
                        else "reports"
                    )
                    enqueue(
                        db,
                        key,
                        page,
                        name.replace("_", " ").title(),
                        body,
                        name == "monthly_pnl",
                        cfg["recipient_emails"],
                    )
                    job.status, job.completed_at, job.last_error = (
                        "success",
                        datetime.utcnow(),
                        None,
                    )
                except Exception as exc:
                    db.rollback()
                    job = db.get(AutomationJob, key)
                    job.status, job.last_error = "failed", type(exc).__name__
                db.commit()
            AutomationRunner.events(db, now, notification_cfg)
            if settings.BACKUP_ENABLED and now.hour >= 2:
                key = f"backup:{now.date()}"
                if claim(db, key):
                    job = db.get(AutomationJob, key)
                    try:
                        result = BackupRunner.run()
                        job.status, job.completed_at, job.last_error = (
                            "success",
                            datetime.utcnow(),
                            None,
                        )
                        subject = "Database backup completed"
                    except Exception as exc:
                        job.status, job.last_error = "failed", type(exc).__name__
                        result, subject = (
                            {"status": "failed", "error": type(exc).__name__},
                            "Database backup failed",
                        )
                    if notification_cfg["notify_backup"]:
                        enqueue(
                            db,
                            key + ":" + job.status,
                            "bank",
                            subject,
                            json.dumps(result),
                            super_only=True,
                        )
                    job.completed_at = datetime.utcnow()
                    db.commit()
            deliver(db)

    @staticmethod
    def events(db, now, cfg):
        today = now.date()
        if cfg["notify_low_stock"]:
            for stock, product in (
                db.query(WarehouseStock, Product)
                .join(Product, Product.id == WarehouseStock.product_id)
                .filter(
                    WarehouseStock.quantity < Product.low_stock_threshold,
                    Product.is_active.is_(True),
                )
                .all()
            ):
                enqueue(
                    db,
                    f"stock:{product.id}:{stock.warehouse_id}:{today}",
                    "warehouse",
                    "Low stock",
                    f"{product.part_code}: {stock.quantity} units remaining",
                    warehouse_id=stock.warehouse_id,
                )
        invoices = db.query(Invoice).filter(
            Invoice.is_cancelled.is_(False),
            Invoice.document_type.in_(["b2b_invoice", "b2c_invoice"]),
        )
        if cfg["notify_overdue"]:
            for inv in invoices.filter(
                Invoice.outstanding_amount > 0, Invoice.due_date < today
            ).all():
                enqueue(
                    db,
                    f"overdue:{inv.id}:{today}",
                    "accounting",
                    "Customer payment overdue",
                    f"Invoice {inv.invoice_number}: outstanding {inv.outstanding_amount}",
                )
        if cfg["notify_large_invoice"]:
            for inv in invoices.filter(
                Invoice.total_amount >= cfg["large_invoice_threshold"],
                Invoice.invoice_date == today,
            ).all():
                enqueue(
                    db,
                    f"large:{inv.id}",
                    "accounting",
                    "Large invoice created",
                    f"Invoice {inv.invoice_number}: {inv.total_amount}",
                )
        if cfg["notify_einvoice_failure"]:
            for entry in (
                db.query(EInvoiceLog).filter(EInvoiceLog.status == "failed").all()
            ):
                enqueue(
                    db,
                    f"gstfailure:{entry.id}",
                    "gst",
                    "E-Invoice generation failed",
                    f"Invoice ID {entry.invoice_id}. Review GST generation logs.",
                )
        if cfg["notify_cheque_bounce"]:
            for cheque in db.query(Cheque).filter(Cheque.status == "bounced").all():
                enqueue(
                    db,
                    f"bounce:{cheque.id}",
                    "accounting",
                    "Cheque bounced",
                    f"Cheque {cheque.cheque_number}: {cheque.amount}",
                )
        if cfg["notify_vendor_due"]:
            for purchase in (
                db.query(Purchase)
                .filter(
                    Purchase.outstanding_amount > 0,
                    Purchase.payment_due_date <= today + timedelta(days=3),
                    Purchase.is_cancelled.is_(False),
                )
                .all()
            ):
                enqueue(
                    db,
                    f"vendor_due:{purchase.id}:{today}",
                    "purchase",
                    "Vendor payment due",
                    f"Purchase {purchase.purchase_number}: {purchase.outstanding_amount}",
                )
        if cfg["notify_unknown_ip"]:
            sessions = (
                db.query(ActiveSession)
                .filter(
                    ActiveSession.login_time >= datetime.utcnow() - timedelta(days=1)
                )
                .all()
            )
            for session in sessions:
                earlier = (
                    db.query(ActiveSession.id)
                    .filter(
                        ActiveSession.user_id == session.user_id,
                        ActiveSession.id < session.id,
                    )
                    .first()
                )
                known = (
                    db.query(ActiveSession.id)
                    .filter(
                        ActiveSession.user_id == session.user_id,
                        ActiveSession.id < session.id,
                        ActiveSession.ip_address == session.ip_address,
                    )
                    .first()
                )
                if earlier and not known:
                    enqueue(
                        db,
                        f"newip:{session.id}",
                        "security",
                        "Login from a new IP",
                        f"User ID {session.user_id}; IP {session.ip_address}",
                    )
        db.commit()


async def automation_loop():
    while True:
        try:
            await asyncio.to_thread(AutomationRunner.tick)
        except Exception:
            log.exception("Automation cycle failed")
        await asyncio.sleep(max(5, settings.AUTOMATION_INTERVAL_SECONDS))
