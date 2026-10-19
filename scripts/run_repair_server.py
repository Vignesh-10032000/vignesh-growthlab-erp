"""Run the repaired ERP against an explicitly isolated local database."""

import os
from pathlib import Path
import sys

from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://erp_user:erp_password@127.0.0.1:3307/wholesale_erp_repair_test",
)

if not (make_url(os.environ["DATABASE_URL"]).database or "").endswith("_repair_test"):
    raise SystemExit("Refusing to run repair tests against a non-repair database")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("AUTOMATION_ENABLED", "false")
os.environ.setdefault("AUTOMATION_EMAIL_ENABLED", "false")
os.environ.setdefault("FRONTEND_URL", "http://127.0.0.1:5197")
os.environ.setdefault("ALLOWED_ORIGINS", '["http://127.0.0.1:5197"]')
os.chdir(root / "backend")
sys.path.insert(0, str(root / "backend"))

if __name__ == "__main__":
    if "--prepare" in sys.argv:
        from app.db.session import Base, engine
        from app.models import models  # noqa: F401

        Base.metadata.create_all(engine)
        print("Isolated repair schema prepared")
        raise SystemExit(0)
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8001)
