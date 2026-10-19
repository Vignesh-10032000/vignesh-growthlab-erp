# Demo ERP repairs

This branch preserves the existing demo login, administrator bootstrap/reset behavior,
and role matrix. Two-factor authentication remains deferred. Existing role checks still
apply when saved page permissions grant a page; those grants cannot override a role.

## Installation

Use the existing Python and frontend dependencies, plus `backend/requirements-dev.txt`
for verification. Before starting the updated backend, run `alembic upgrade head` from
`backend` with the intended `DATABASE_URL`. The new revision is `20261019_repairs`.
The migration creates only the automation and opening-submission tables. It does not
repost historical balances or change user credentials or roles.

Opening balances now use `/api/v1/opening-balances/`. They post FIFO stock, party
ledgers, and a balanced journal against opening equity in one transaction. A repeated
submission identifier returns its previous result; changed payloads or repeated
FY/entity openings return a conflict. CSV imports validate every row before posting.
Correcting an already posted opening requires an accounting correction; editing the
same entry and submitting it again does not silently replace historical balances.

## Automation

The application runs its scheduler through FastAPI lifespan; Redis and Celery are not
required. Database leases and execution keys coordinate multiple API workers. Existing
temporary-file notification/report settings are imported once when automation starts.
SMTP passwords are encrypted using a key derived from `SECRET_KEY`, and API reads
return an empty password plus `smtp_password_configured`. After rotating the deployment
secret, re-enter the SMTP password.

Available environment settings:

```dotenv
AUTOMATION_ENABLED=true
AUTOMATION_INTERVAL_SECONDS=30
AUTOMATION_EMAIL_ENABLED=false
AUTOMATION_SMTP_TLS=true
BACKUP_ENABLED=false
BACKUP_DIR=./backups
BACKUP_RETENTION_DAYS=30
BACKUP_DUMP_EXECUTABLE=mariadb-dump
BACKUP_TIMEOUT_SECONDS=300
```

Email and backups are opt-in. Configure SMTP through Bank → Notifications and enable
email delivery in the deployment environment. Only active ERP users can be selected.
Delivery rechecks the user's current permissions. P&L is exclusive to Super Admin;
company-wide reports exclude users restricted to individual warehouses. Notification
emails are selected through the saved administrator/accountant addresses; scheduled
reports use their saved recipient list. The notification bell shows each user's inbox.
Delivery failures are retried at most three times; SMTP delivery can be repeated after
a process crash between sending a message and persisting confirmation.

Schedules use Asia/Kolkata: daily at the configured time, weekly on Monday, monthly
reports on the first, and the bank-statement reminder on the 25th. The latest due
weekly/monthly period is processed once after restart. Monthly stock is the stock
snapshot at execution time, not a reconstructed historical stock snapshot.

For backups, provide a persistent directory writable by the application, a compatible
MariaDB/MySQL dump executable, and database privileges for routines/triggers. Set
`BACKUP_ENABLED=true`. Backups run daily at 02:00 and retain 30 days. Super Admin can
also run one through Bank → Backup Status. Credentials are passed through a private
temporary option file and removed afterward. Restore into an explicitly chosen
database; no restore endpoint is exposed by the web application.

GST stays in the existing sandbox configuration. No live GST credentials are added.

## Local verification

Create `wholesale_erp_repair_test` and grant the test database account access to that
database only. The default test connection is local MariaDB on port 3307. Override
`DATABASE_URL` as needed; the test runner requires a database ending in `_repair_test`.
Use a database dedicated to these tests: fixtures remove synthetic transaction records.

Initialize a fresh test schema with `python scripts/run_repair_server.py --prepare`, then run
`python scripts/run_repair_server.py` from the repository root. The API uses port 8001,
with automatic external email, backups, and the scheduler disabled. Apply migrations
to this isolated database when checking upgrade/rollback behavior.

```powershell
python -m pytest tests/repair -q
cd frontend
npm ci
npm run test:e2e
```

Playwright starts an isolated frontend at port 5197 and targets the test API. Run the
pytest fixtures first. Tests cover Chromium desktop and mobile, real login and reload,
role restrictions, saved permissions, opening-stock posting, and settings persistence.
The backup/restore test expects local MariaDB utilities and a test database administrator;
it creates only `wholesale_erp_restore_repair_test` for restoration.

For Keploy, run `python scripts/capture_keploy_repairs.py` after the API tests. Import
the resulting Postman collection locally with `keploy import postman -p collection.json`
from `test-results/keploy-api-verified`, then replay against port 8001 with `keploy test --base-path`.
On this Windows machine, Keploy 3.8.69 is already installed in Ubuntu/WSL. Use the Windows
host address reachable from WSL as the base path. The suite calls the real isolated API
and database; it does not mock outgoing SQL. Captures contain disposable test tokens,
remain ignored by Git, and must not be uploaded. `coverage.json` lists captured and
uncaptured API operations; a successful replay is not a claim of full API coverage.

Reports and artifacts are written under ignored `test-results/`, including pytest XML,
Playwright HTML/traces, Keploy YAML reports, and security-scan JSON.
