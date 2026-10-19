# Repair verification — 19 October 2026

Branch: `codex/erp-demo-repairs`, based on `0801e8f`.
Verification used a dedicated MariaDB database ending in `_repair_test`, API port
8001, and frontend port 5197. The original ERP checkout, running application, and
business database were not replaced.

| Check | Status | Evidence |
|---|---|---|
| API and integration regressions | VERIFIED | 31 pytest tests passed; XML under `test-results/pytest.xml` |
| Randomized financial inputs | VERIFIED | Eight Hypothesis examples exercised real opening postings; SymPy checked debit/credit equality |
| Keploy 3.8.69 replay | VERIFIED | 37/37 captured requests passed against the real isolated API/database |
| Frontend workflows | VERIFIED | 10/10 Chromium desktop and mobile Playwright tests passed |
| Production frontend build | VERIFIED | Vite build completed; existing chunk-size/import warnings remain |
| Database migration | VERIFIED | Upgrade, downgrade to `20260617_transport`, and upgrade to `20261019_repairs` completed on the isolated database |
| Backup restoration | VERIFIED | Actual compressed MariaDB dump restored into `wholesale_erp_restore_repair_test` |
| SMTP delivery and failures | VERIFIED | A local SMTP receiver accepted delivery; retry exhaustion and error redaction were checked |
| Security scan | VERIFIED | Linux Semgrep 1.181.0 ran 219 rules on seven relevant files: zero findings and zero scan errors |
| Python lint and compilation | VERIFIED | Scoped Ruff E4/E7/E9/F checks and backend compilation passed |
| Demo authentication preservation | VERIFIED | AST comparison confirmed `login` and `_ensure_default_superadmin` unchanged from main |
| Final API error log | VERIFIED | No HTTP 500 or application error entries during the final API tests and replay |
| Static type checking | NOT VERIFIED | This JavaScript/Python repository does not configure a static type-checking gate; build, lint, and runtime verification were used |
| Real external email / live GST | NOT VERIFIED | Tests used local SMTP and the existing GST sandbox; real external delivery was not enabled |
| Production rollout | NOT VERIFIED | Changes are prepared on a branch; no merge or deployment performed |

Coverage is deliberately bounded. The Keploy collection has 37 role/behavior cases
across 16 distinct method/path pairs, including `/health`. The live schema has 243
API operations; this is not 100% API coverage. The generated coverage inventory lists
uncaptured operations. No claim is made that every ERP business workflow was tested.

The first Keploy import exposed case-sensitive HTTP header comparisons and fixture
stock changing after read snapshots. The capture adapter now canonicalizes header
names and settles opening-stock fixtures before recording reads. Only transport Date
and Connection headers are excluded; business values and authorization results are
compared. The final passing reports are under `test-results/keploy-api-final/`.

Windows Semgrep failed in its native engine; the successful scan was run in WSL.
The scan covers the new permission/opening/automation modules, the affected accounting
and stock-report services, and the new frontend notification/access components. It is
not a full repository security audit. npm installation reported 21 dependency audit
findings; dependency upgrades were not included in these feature repairs.

Raw Keploy captures contain disposable test tokens and stay ignored by Git. Backups,
browser traces, and local runtime logs also remain uncommitted. See
[setup and operation](ERP_REPAIR_SETUP.md) for required migration, opt-in email/backup
configuration, and reproducible test commands.
