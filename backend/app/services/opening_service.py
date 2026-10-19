import hashlib
import json
import time
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.models import (
    Account,
    Customer,
    Vendor,
    Warehouse,
    Product,
    StockEntry,
    StockTransactionType,
    LedgerEntry,
    TransactionType,
    JournalEntry,
    JournalLine,
    OpeningSubmission,
    OpeningEntry,
)
from app.services.product_service import StockService
from app.utils.helpers import get_financial_year


class OpeningPostingService:
    @staticmethod
    def create(db, payload, user_id):
        for attempt in range(4):
            try:
                return OpeningPostingService._create(db, payload, user_id)
            except OperationalError as exc:
                db.rollback()
                code = getattr(exc.orig, "args", (None,))[0]
                if code not in (1020, 1205, 1213) or attempt == 3:
                    raise
                time.sleep(0.05 * (2**attempt))

    @staticmethod
    def _create(db, payload, user_id):
        encoded = payload.model_dump_json(exclude={"submission_id"})
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        key = payload.submission_id or digest
        existing = db.get(OpeningSubmission, key)
        if existing:
            if existing.created_by != user_id or existing.payload_hash != digest:
                raise HTTPException(
                    409, "Submission identifier already used for different data"
                )
            return json.loads(existing.response_json)
        if get_financial_year(payload.opening_date) != payload.financial_year:
            raise HTTPException(
                422, "Opening date must belong to the selected financial year"
            )
        specs = []
        for kind, values, model, id_attr in (
            ("stock", payload.stock_items, Product, "product_id"),
            ("customer", payload.customer_balances, Customer, "customer_id"),
            ("vendor", payload.vendor_balances, Vendor, "vendor_id"),
        ):
            for item in values:
                entity_id = getattr(item, id_attr)
                entity = db.get(model, entity_id)
                if not entity or not getattr(entity, "is_active", True):
                    raise HTTPException(422, f"Invalid or inactive {kind}: {entity_id}")
                if item.opening_date != payload.opening_date:
                    raise HTTPException(
                        422, "All opening dates must match the submission date"
                    )
                identity = f"{payload.financial_year}:{kind}:{entity_id}"
                if kind == "stock":
                    wh = db.get(Warehouse, item.warehouse_id)
                    if not wh or not wh.is_active:
                        raise HTTPException(422, "Invalid or inactive warehouse")
                    identity += f":{item.warehouse_id}"
                    old = (
                        db.query(StockEntry.id)
                        .filter(
                            StockEntry.product_id == entity_id,
                            StockEntry.warehouse_id == item.warehouse_id,
                            StockEntry.reference_type == "opening_balance",
                            StockEntry.batch_date == payload.opening_date,
                        )
                        .first()
                    )
                else:
                    old = (
                        db.query(LedgerEntry.id)
                        .filter(
                            getattr(LedgerEntry, id_attr) == entity_id,
                            LedgerEntry.reference_type == "opening_balance",
                            LedgerEntry.financial_year == payload.financial_year,
                        )
                        .first()
                    )
                if old:
                    raise HTTPException(
                        409, f"Opening already posted for {kind} {entity_id}"
                    )
                specs.append((identity, kind, item))
        if payload.cash_balance:
            specs.append(
                (f"{payload.financial_year}:cash", "cash", payload.cash_balance)
            )
        for bank in payload.bank_balances:
            if not bank.account_code.strip():
                raise HTTPException(422, "Bank account code is required")
            specs.append(
                (f"{payload.financial_year}:bank:{bank.account_code}", "bank", bank)
            )
        for kind in ("other_assets", "other_liabilities"):
            if getattr(payload, kind):
                specs.append(
                    (f"{payload.financial_year}:{kind}", kind, getattr(payload, kind))
                )
        if not specs:
            raise HTTPException(422, "Enter at least one opening balance")
        keys = [s[0] for s in specs]
        if (
            len(keys) != len(set(keys))
            or db.query(OpeningEntry.key).filter(OpeningEntry.key.in_(keys)).first()
        ):
            raise HTTPException(
                409, "Duplicate opening balance for the selected financial year"
            )
        try:
            db.add(OpeningSubmission(key=key, payload_hash=digest, created_by=user_id))
            db.flush()
            for identity, _, _ in specs:
                db.add(OpeningEntry(key=identity, submission_key=key))
            db.flush()
            journal = JournalEntry(
                entry_number=f"OB-{hashlib.sha256(key.encode()).hexdigest()[:24]}",
                entry_date=payload.opening_date,
                reference_type="opening_balance",
                narration="Opening balances",
                financial_year=payload.financial_year,
                created_by=user_id,
            )
            db.add(journal)
            db.flush()
            totals = {}
            created = {"stock": 0, "customers": 0, "vendors": 0, "cash": 0, "bank": 0}

            def add(code, amount, credit=False):
                totals[code] = totals.get(code, Decimal("0")) + (
                    -amount if credit else amount
                )

            for _, kind, item in specs:
                if kind == "stock":
                    entry = StockService.add_stock(
                        db,
                        item.product_id,
                        item.warehouse_id,
                        item.quantity,
                        item.unit_cost,
                        StockTransactionType.adjustment_in,
                        "opening_balance",
                        journal.id,
                        item.opening_date,
                        user_id,
                    )
                    entry.entry_date = item.opening_date
                    add(
                        "STOCK",
                        (item.quantity * item.unit_cost).quantize(Decimal("0.01")),
                    )
                    created["stock"] += 1
                elif kind in ("customer", "vendor"):
                    is_vendor = kind == "vendor"
                    db.add(
                        LedgerEntry(
                            customer_id=None if is_vendor else item.customer_id,
                            vendor_id=item.vendor_id if is_vendor else None,
                            transaction_type="credit" if is_vendor else "debit",
                            amount=item.opening_balance,
                            balance=item.opening_balance,
                            reference_type="opening_balance",
                            reference_id=journal.id,
                            narration="Opening balance",
                            entry_date=item.opening_date,
                            financial_year=payload.financial_year,
                        )
                    )
                    add(
                        "CREDITORS" if is_vendor else "DEBTORS",
                        item.opening_balance,
                        is_vendor,
                    )
                    created["vendors" if is_vendor else "customers"] += 1
                elif kind in ("cash", "bank"):
                    if item.opening_date != payload.opening_date:
                        raise HTTPException(
                            422, "All opening dates must match the submission date"
                        )
                    code = "CASH" if kind == "cash" else item.account_code
                    acc = OpeningPostingService.account(db, code, "asset", user_id)
                    acc.opening_balance = item.amount
                    add(code, item.amount)
                    created[kind] += 1
                else:
                    add(
                        "OTHER_ASSETS"
                        if kind == "other_assets"
                        else "OTHER_LIABILITIES",
                        item,
                        kind == "other_liabilities",
                    )
            add("OPENING_EQUITY", sum(totals.values()), True)
            for code, net in totals.items():
                if not net:
                    continue
                atype = (
                    "equity"
                    if code == "OPENING_EQUITY"
                    else (
                        "liability"
                        if code in ("CREDITORS", "OTHER_LIABILITIES")
                        else "asset"
                    )
                )
                account = OpeningPostingService.account(db, code, atype, user_id)
                db.add(
                    JournalLine(
                        journal_entry_id=journal.id,
                        account_id=account.id,
                        transaction_type=TransactionType.debit
                        if net > 0
                        else TransactionType.credit,
                        amount=abs(net),
                        narration="Opening balance",
                    )
                )
            result = {
                "message": "Opening balances created successfully",
                "created": created,
                "financial_year": payload.financial_year,
                "submission_id": key,
                "journal_entry_id": journal.id,
            }
            db.get(OpeningSubmission, key).response_json = json.dumps(result)
            db.commit()
            return result
        except IntegrityError:
            db.rollback()
            existing = db.get(OpeningSubmission, key)
            if (
                existing
                and existing.created_by == user_id
                and existing.payload_hash == digest
            ):
                return json.loads(existing.response_json)
            raise HTTPException(409, "Opening balance already posted")
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def account(db, code, account_type, user_id):
        account = db.query(Account).filter(Account.account_code == code).first()
        if not account:
            account = Account(
                account_code=code,
                name=code.replace("_", " ").title(),
                account_name=code.replace("_", " ").title(),
                account_type=account_type,
                is_active=True,
                opening_balance=0,
                current_balance=0,
                created_by=user_id,
            )
            db.add(account)
            db.flush()
        return account
