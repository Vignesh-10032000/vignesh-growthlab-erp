from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import User
from app.core.security import get_current_user, require_admin, require_admin_or_accountant, require_super_admin
from app.schemas.bank import (
    BankStockStatementCreate, BankReconciliationImport,
    NotificationSettingsUpdate, ScheduledReportSettings,
    BankReconCreate, ManualMatchRequest, UnmatchRequest, AdjustmentRequest,
)
from app.services.bank_service import (
    BankStockStatementService, BankReconciliationService,
    NotificationService, ScheduledReportService, BackupService,
)
from app.services.bank_recon_service import BankReconService

bank_stmt_router = APIRouter(prefix="/bank-stock-statement", tags=["bank-statement"])

@bank_stmt_router.get("/")
async def list_statements(page: int = Query(1, ge=1), page_size: int = Query(20), db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankStockStatementService.list_statements(db, page, page_size)

@bank_stmt_router.post("/", status_code=201)
async def generate_statement(payload: BankStockStatementCreate, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankStockStatementService.generate(db, payload, current_user.id)

@bank_stmt_router.get("/{stmt_id}")
async def get_statement(stmt_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankStockStatementService.get_by_id(db, stmt_id)

bank_recon_router = APIRouter(prefix="/bank-reconciliation", tags=["bank-reconciliation"])

@bank_recon_router.post("/reconcile")
async def reconcile_bank(payload: BankReconciliationImport, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconciliationService.reconcile(db, payload)


@bank_recon_router.post("/", status_code=201)
async def create_reconciliation(payload: BankReconCreate, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.create_draft(db, payload, current_user.id)


@bank_recon_router.get("/")
async def list_reconciliations(page: int = Query(1, ge=1), page_size: int = Query(20), db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankReconService.list_recons(db, page, page_size)


@bank_recon_router.get("/{recon_id}")
async def get_reconciliation(recon_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin_or_accountant)):
    return BankReconService.get(db, recon_id)


@bank_recon_router.post("/{recon_id}/match")
async def match_line(recon_id: int, payload: ManualMatchRequest, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.manual_match(db, recon_id, payload.line_id, payload.journal_line_id, current_user.id)


@bank_recon_router.post("/{recon_id}/unmatch")
async def unmatch_line(recon_id: int, payload: UnmatchRequest, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.unmatch(db, recon_id, payload.line_id, current_user.id)


@bank_recon_router.post("/{recon_id}/adjustment")
async def add_adjustment(recon_id: int, payload: AdjustmentRequest, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.add_adjustment(db, recon_id, payload, current_user.id)


@bank_recon_router.post("/{recon_id}/finalize")
async def finalize_reconciliation(recon_id: int, current_user: User = Depends(require_admin_or_accountant), db: Session = Depends(get_db)):
    return BankReconService.finalize(db, recon_id, current_user.id)


@bank_recon_router.post("/import-file")
async def import_statement_file(file: UploadFile = File(...), _: User = Depends(require_admin_or_accountant)):
    content = await file.read()
    entries = BankReconService.parse_statement_file(file.filename, content)
    return {"entries": entries, "count": len(entries)}

notification_router = APIRouter(prefix="/notifications", tags=["notifications"])

@notification_router.get("/settings")
async def get_notification_settings(_: User = Depends(require_admin)):
    return NotificationService.get_settings()

@notification_router.put("/settings")
async def update_notification_settings(payload: NotificationSettingsUpdate, _: User = Depends(require_admin)):
    return NotificationService.update_settings(payload)

@notification_router.post("/test-email")
async def test_email(payload: dict, _: User = Depends(require_admin)):
    return NotificationService.test_email(payload.get("to_email", ""))

scheduled_router = APIRouter(prefix="/scheduled-reports", tags=["scheduled-reports"])

@scheduled_router.get("/settings")
async def get_scheduled_settings(_: User = Depends(require_admin)):
    return ScheduledReportService.get_settings()

@scheduled_router.put("/settings")
async def update_scheduled_settings(payload: ScheduledReportSettings, _: User = Depends(require_admin)):
    return ScheduledReportService.update_settings(payload)

backup_router = APIRouter(prefix="/backup", tags=["backup"])

@backup_router.get("/status")
async def get_backup_status(_: User = Depends(require_admin)):
    return BackupService.get_status()


@notification_router.get("/")
async def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.models import UserNotification
    from app.services.automation_service import eligible
    rows = db.query(UserNotification).filter(UserNotification.user_id == user.id).order_by(UserNotification.id.desc()).all()
    visible = [r for r in rows if eligible(user, r.page_key, r.event_key.startswith("report:monthly_pnl"), r.warehouse_id)]
    return {"unread_count": sum(not r.is_read for r in visible), "items": [
        {"id": r.id, "subject": r.subject, "body": r.body, "is_read": r.is_read,
         "email_status": r.email_status, "created_at": r.created_at} for r in visible[:50]]}


@notification_router.patch("/{notification_id}/read")
async def read_notification(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.models import UserNotification
    row = db.query(UserNotification).filter_by(id=notification_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Notification not found")
    row.is_read = True
    db.commit()
    return {"id": row.id, "is_read": True}


@scheduled_router.get("/status")
async def scheduled_status(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    from app.models.models import AutomationJob
    from app.core.config import settings
    rows = db.query(AutomationJob).order_by(AutomationJob.key.desc()).limit(30).all()
    return {"scheduler_enabled": settings.AUTOMATION_ENABLED, "email_delivery_enabled": settings.AUTOMATION_EMAIL_ENABLED,
            "timezone": "Asia/Kolkata", "jobs": [{"key": r.key, "status": r.status, "attempts": r.attempts,
            "last_error": r.last_error, "completed_at": r.completed_at} for r in rows]}


@backup_router.post("/run")
async def run_backup(user: User = Depends(require_super_admin)):
    import asyncio
    from app.services.automation_service import BackupRunner
    return await asyncio.to_thread(BackupRunner.run_manual)
