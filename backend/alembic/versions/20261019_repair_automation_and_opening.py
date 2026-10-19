"""Persistent automation and idempotent opening balances."""
from alembic import op
from app.models.models import (
    AutomationSetting, AutomationJob, UserNotification, OpeningSubmission, OpeningEntry,
)

revision = "20261019_repairs"
down_revision = "20260617_transport"
branch_labels = None
depends_on = None


def upgrade():
    for model in (AutomationSetting, AutomationJob, UserNotification, OpeningSubmission, OpeningEntry):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (OpeningEntry, OpeningSubmission, UserNotification, AutomationJob, AutomationSetting):
        model.__table__.drop(op.get_bind(), checkfirst=True)
