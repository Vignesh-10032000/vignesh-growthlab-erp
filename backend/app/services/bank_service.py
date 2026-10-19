from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi import HTTPException
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List
import os, json

from app.models.models import (
    BankStockStatement, StockEntry, Product, Warehouse,
    Invoice, Customer, DocumentType, LedgerEntry,
    TransactionType, User
)
from app.schemas.bank import (
    BankStockStatementCreate, BankReconciliationImport,
    NotificationSettingsUpdate, ScheduledReportSettings
)
from app.utils.helpers import paginate, get_financial_year, format_document_number
from app.services.audit import audit
from app.services.config_service import ConfigService


class BankStockStatementService:

    @staticmethod
    def _calc_stock_value(db, as_of_date):
        entries = db.query(StockEntry, Product, Warehouse).join(
            Product, StockEntry.product_id == Product.id
        ).join(
            Warehouse, StockEntry.warehouse_id == Warehouse.id
        ).filter(
            StockEntry.entry_date <= as_of_date,
            StockEntry.remaining_qty > 0,
            Product.is_active == True,
            Warehouse.is_active == True,
        ).all()

        total_value = Decimal("0")
        breakup = {}
        for se, prod, wh in entries:
            val = se.remaining_qty * se.unit_cost
            total_value += val
            key = f"{prod.id}_{wh.id}"
            if key not in breakup:
                breakup[key] = {
                    "part_code": prod.part_code,
                    "part_name": prod.part_name,
                    "warehouse_name": wh.name,
                    "quantity": Decimal("0"),
                    "value": Decimal("0"),
                }
            breakup[key]["quantity"] += se.remaining_qty
            breakup[key]["value"] += val

        result = []
        for item in breakup.values():
            result.append({
                "part_code": item["part_code"],
                "part_name": item["part_name"],
                "warehouse_name": item["warehouse_name"],
                "quantity": float(item["quantity"]),
                "value": float(item["value"].quantize(Decimal("0.01"))),
            })
        return total_value.quantize(Decimal("0.01")), result

    @staticmethod
    def _calc_debtors(db, as_of_date):
        invoices = db.query(Invoice, Customer).join(
            Customer, Invoice.customer_id == Customer.id
        ).filter(
            Invoice.invoice_date <= as_of_date,
            Invoice.is_cancelled == False,
            Invoice.document_type.in_([DocumentType.b2b_invoice, DocumentType.b2c_invoice]),
            Invoice.outstanding_amount > 0,
        ).all()

        total = Decimal("0")
        breakup = []
        for inv, cust in invoices:
            total += inv.outstanding_amount
            breakup.append({
                "customer_name": cust.trade_name,
                "invoice_number": inv.invoice_number,
                "invoice_date": str(inv.invoice_date),
                "outstanding": float(inv.outstanding_amount),
            })
        return total.quantize(Decimal("0.01")), breakup

    @staticmethod
    def generate(db, payload: BankStockStatementCreate, user_id: int) -> dict:
        stock_value, stock_breakup = BankStockStatementService._calc_stock_value(db, payload.statement_date)
        debtors_value, debtor_breakup = BankStockStatementService._calc_debtors(db, payload.statement_date)
        total_value = stock_value + debtors_value
        margin_pct = payload.margin_percent
        if margin_pct is None:
            margin_pct = ConfigService.get_decimal(
                db, "rbi.bank_stock_margin",
                as_of=payload.statement_date, default=Decimal("25"),
            )
        margin = Decimal(str(margin_pct)) / 100
        drawing_power = (total_value * (1 - margin)).quantize(Decimal("0.01"))
        fy = get_financial_year(payload.statement_date)
        count = db.query(BankStockStatement).count()
        stmt_number = format_document_number(db, "BSS", fy, count + 1, "BSS", 4)

        stmt = BankStockStatement(
            statement_number=stmt_number,
            statement_date=payload.statement_date,
            statement_month=payload.statement_date.strftime("%Y-%m"),
            bank_name=payload.bank_name,
            account_number=payload.account_number,
            stock_value=stock_value,
            debtors_value=debtors_value,
            total_value=total_value,
            margin_percent=margin_pct,
            drawing_power=drawing_power,
            cc_limit=payload.cc_limit,
            is_locked=True,
            notes=payload.notes,
            stock_breakup=json.dumps(stock_breakup),
            debtor_breakup=json.dumps(debtor_breakup),
            financial_year=fy,
            created_by=user_id,
        )
        db.add(stmt)
        db.commit()
        db.refresh(stmt)

        audit(db, user_id, "create", "bank",
              f"Generated bank stock statement {stmt.statement_number} ({stmt.bank_name}) "
              f"— drawing power ₹{stmt.drawing_power}",
              record_type="bank_stock_statement", record_id=stmt.id)

        u = db.query(User).filter(User.id == user_id).first()
        return BankStockStatementService._fmt(stmt, stock_breakup, debtor_breakup[:50], u)

    @staticmethod
    def list_statements(db, page=1, page_size=20) -> dict:
        q = db.query(BankStockStatement).order_by(desc(BankStockStatement.statement_date))
        result = paginate(q, page, page_size)
        items = []
        for stmt in result["items"]:
            u = db.query(User).filter(User.id == stmt.created_by).first()
            items.append({
                "id": stmt.id, "statement_number": stmt.statement_number,
                "statement_date": stmt.statement_date, "bank_name": stmt.bank_name,
                "account_number": stmt.account_number, "stock_value": stmt.stock_value,
                "debtors_value": stmt.debtors_value, "drawing_power": stmt.drawing_power,
                "cc_limit": stmt.cc_limit, "is_locked": stmt.is_locked,
                "financial_year": stmt.financial_year, "created_at": stmt.created_at,
                "generated_by_name": u.full_name if u else None,
            })
        result["items"] = items
        return result

    @staticmethod
    def get_by_id(db, stmt_id: int) -> dict:
        stmt = db.query(BankStockStatement).filter(BankStockStatement.id == stmt_id).first()
        if not stmt:
            raise HTTPException(status_code=404, detail="Statement not found")
        u = db.query(User).filter(User.id == stmt.created_by).first()
        try:
            sb = json.loads(stmt.stock_breakup) if stmt.stock_breakup else []
            db2 = json.loads(stmt.debtor_breakup) if stmt.debtor_breakup else []
        except Exception:
            sb, db2 = [], []
        return BankStockStatementService._fmt(stmt, sb, db2, u)

    @staticmethod
    def _fmt(stmt, stock_breakup, debtor_breakup, u) -> dict:
        return {
            "id": stmt.id, "statement_number": stmt.statement_number,
            "statement_date": stmt.statement_date, "bank_name": stmt.bank_name,
            "account_number": stmt.account_number, "stock_value": stmt.stock_value,
            "debtors_value": stmt.debtors_value, "total_value": stmt.total_value,
            "margin_percent": stmt.margin_percent, "drawing_power": stmt.drawing_power,
            "cc_limit": stmt.cc_limit, "is_locked": stmt.is_locked, "notes": stmt.notes,
            "stock_breakup": stock_breakup, "debtor_breakup": debtor_breakup,
            "financial_year": stmt.financial_year, "created_at": stmt.created_at,
            "generated_by_name": u.full_name if u else None,
            "declaration": (
                "We hereby declare that the above stock statement is true and correct "
                "to the best of our knowledge and belief. The above stock is free from "
                "any charge, lien or encumbrance except those in favour of the bank."
            ),
        }


class BankReconciliationService:

    @staticmethod
    def reconcile(db, payload: BankReconciliationImport) -> dict:
        ledger_entries = db.query(LedgerEntry).filter(
            LedgerEntry.entry_date >= payload.period_from,
            LedgerEntry.entry_date <= payload.period_to,
        ).all()

        recon_tol = ConfigService.get_decimal(
            db, "rbi.recon_amount_tolerance",
            as_of=payload.period_from, default=Decimal("1"))
        recon_window = ConfigService.get_int(
            db, "rbi.recon_date_window_days",
            as_of=payload.period_from, default=2)

        auto_matched, unmatched_bank = [], []
        used_ledger = set()
        bank_credit = bank_debit = Decimal("0")

        for bank_entry in payload.entries:
            bank_credit += bank_entry.credit or Decimal("0")
            bank_debit += bank_entry.debit or Decimal("0")
            matched = False
            for j, le in enumerate(ledger_entries):
                if j in used_ledger:
                    continue
                bank_amount = bank_entry.credit if le.transaction_type == TransactionType.credit else bank_entry.debit
                if bank_amount and abs(le.amount - bank_amount) < recon_tol and abs((le.entry_date - bank_entry.entry_date).days) <= recon_window:
                    auto_matched.append({
                        "bank_entry": {"date": str(bank_entry.entry_date), "description": bank_entry.description, "amount": float(bank_amount)},
                        "ledger_entry_id": le.id, "narration": le.narration, "amount": float(le.amount),
                    })
                    used_ledger.add(j)
                    matched = True
                    break
            if not matched:
                unmatched_bank.append({"date": str(bank_entry.entry_date), "description": bank_entry.description, "debit": float(bank_entry.debit or 0), "credit": float(bank_entry.credit or 0)})

        unmatched_books = [
            {"ledger_entry_id": ledger_entries[j].id, "date": str(ledger_entries[j].entry_date), "narration": ledger_entries[j].narration, "amount": float(ledger_entries[j].amount)}
            for j in range(len(ledger_entries)) if j not in used_ledger
        ]

        bank_closing = bank_credit - bank_debit
        books_debit = sum(le.amount for le in ledger_entries if le.transaction_type == TransactionType.debit)
        books_credit = sum(le.amount for le in ledger_entries if le.transaction_type == TransactionType.credit)
        books_closing = books_credit - books_debit

        return {
            "bank_account_code": payload.bank_account_code,
            "period_from": payload.period_from, "period_to": payload.period_to,
            "auto_matched": auto_matched, "unmatched_in_bank": unmatched_bank,
            "unmatched_in_books": unmatched_books,
            "matched_count": len(auto_matched),
            "unmatched_bank_count": len(unmatched_bank),
            "unmatched_books_count": len(unmatched_books),
            "bank_closing_balance": float(bank_closing),
            "books_closing_balance": float(books_closing),
            "difference": float(bank_closing - books_closing),
        }


class NotificationService:
    @staticmethod
    def get_settings():
        from app.db.session import SessionLocal
        from app.services.automation_service import AutomationSettings
        with SessionLocal() as db:
            return AutomationSettings.get(db, "notifications")

    @staticmethod
    def update_settings(payload):
        from app.db.session import SessionLocal
        from app.services.automation_service import AutomationSettings
        with SessionLocal() as db:
            return AutomationSettings.update(db, "notifications", payload)

    @staticmethod
    def test_email(to_email):
        from app.db.session import SessionLocal
        from app.services.automation_service import AutomationSettings, send_email
        from fastapi import HTTPException
        from sqlalchemy import func
        with SessionLocal() as db:
            AutomationSettings.validate_recipients(db, [to_email])
            user = db.query(User).filter(func.lower(User.email) == to_email.lower(), User.is_active.is_(True)).first()
            try:
                send_email(db, user, "ERP test email", "Email delivery is configured correctly.")
                return {"success": True, "message": "Test email sent"}
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(502, "SMTP delivery failed; check configuration and server availability")


class ScheduledReportService:
    @staticmethod
    def get_settings():
        from app.db.session import SessionLocal
        from app.services.automation_service import AutomationSettings
        with SessionLocal() as db:
            return AutomationSettings.get(db, "reports")

    @staticmethod
    def update_settings(payload):
        from app.db.session import SessionLocal
        from app.services.automation_service import AutomationSettings
        with SessionLocal() as db:
            return AutomationSettings.update(db, "reports", payload)


class BackupService:
    @staticmethod
    def get_status():
        from app.services.automation_service import BackupRunner
        from app.models.models import AutomationJob
        from app.db.session import SessionLocal
        status = BackupRunner.status()
        with SessionLocal() as db:
            last = db.query(AutomationJob).filter(AutomationJob.key.like("backup:%")).order_by(AutomationJob.completed_at.desc()).first()
            if last:
                status["last_attempt_status"] = last.status
                status["last_attempt_error"] = last.last_error
        return status
