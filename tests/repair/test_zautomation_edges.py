from datetime import date, datetime, timedelta
import socket
import uuid

from aiosmtpd.controller import Controller
from sympy import Rational

from app.core.config import settings
from app.models.models import (
    User,
    UserNotification,
    Invoice,
    Purchase,
    Cheque,
    EInvoiceLog,
    JournalLine,
)
from app.schemas.bank import NotificationSettingsUpdate
from app.services.automation_service import (
    AutomationSettings,
    AutomationRunner,
    enqueue,
    deliver,
    IST,
    NOTIFICATION_DEFAULTS,
)


def test_real_local_smtp_delivery(db, monkeypatch):
    class Sink:
        messages = []

        async def handle_DATA(self, server, session, envelope):
            self.messages.append(envelope.content)
            return "250 OK"

    with socket.socket() as socket_handle:
        socket_handle.bind(("127.0.0.1", 0))
        port = socket_handle.getsockname()[1]
    sink = Sink()
    controller = Controller(sink, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        user = db.query(User).filter_by(username="repair_admin").one()
        monkeypatch.setattr(settings, "AUTOMATION_EMAIL_ENABLED", True)
        monkeypatch.setattr(settings, "AUTOMATION_SMTP_TLS", False)
        AutomationSettings.update(
            db,
            "notifications",
            NotificationSettingsUpdate(
                smtp_host="127.0.0.1",
                smtp_port=port,
                smtp_username="",
                smtp_from_email="erp@example.test",
                admin_email=user.email,
            ),
        )
        key = "repair:smtp:" + uuid.uuid4().hex
        enqueue(
            db,
            key,
            "accounting",
            "Local SMTP test",
            "Synthetic notification",
            recipients=[user.email],
        )
        db.commit()
        deliver(db)
        row = db.query(UserNotification).filter_by(event_key=key, user_id=user.id).one()
        assert row.email_status == "sent"
        assert any(b"Synthetic notification" in message for message in sink.messages)
    finally:
        controller.stop()


def test_notification_events_are_deduplicated(db):
    today = date.today()
    invoice = Invoice(
        invoice_number="RPR-EVENT",
        document_type="b2b_invoice",
        warehouse_id=1,
        customer_id=1,
        total_amount=150000,
        outstanding_amount=150000,
        invoice_date=today,
        due_date=today - timedelta(days=1),
        is_cancelled=False,
    )
    purchase = Purchase(
        purchase_number="RPR-EVENT-P",
        vendor_id=1,
        warehouse_id=1,
        outstanding_amount=100,
        payment_due_date=today + timedelta(days=1),
        is_cancelled=False,
    )
    db.add_all([invoice, purchase])
    db.flush()
    db.add_all(
        [
            EInvoiceLog(invoice_id=invoice.id, status="failed"),
            Cheque(
                cheque_number="RPR-CHEQUE",
                cheque_date=today,
                bank_name="Repair Bank",
                amount=10,
                status="bounced",
            ),
        ]
    )
    db.commit()
    now = datetime.now(IST)
    AutomationRunner.events(db, now, NOTIFICATION_DEFAULTS)
    first = db.query(UserNotification).count()
    AutomationRunner.events(db, now, NOTIFICATION_DEFAULTS)
    assert db.query(UserNotification).count() == first
    for prefix in (
        "overdue:",
        "large:",
        "vendor_due:",
        "gstfailure:",
        "bounce:",
        "stock:",
    ):
        assert (
            db.query(UserNotification)
            .filter(UserNotification.event_key.like(prefix + "%"))
            .count()
            > 0
        )


def test_journal_math_independently_with_sympy(db):
    journal_ids = [row[0] for row in db.query(JournalLine.journal_entry_id).distinct()]
    for journal_id in journal_ids:
        balance = sum(
            (
                Rational(str(line.amount))
                * (1 if line.transaction_type == "debit" else -1)
                for line in db.query(JournalLine).filter_by(journal_entry_id=journal_id)
            ),
            Rational(0),
        )
        assert balance == 0
