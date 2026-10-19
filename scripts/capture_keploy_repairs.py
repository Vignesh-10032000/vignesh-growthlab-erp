"""Capture independently checked, disposable ERP API cases for local Keploy replay."""

import json
import os
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8001"
OUT = Path(__file__).resolve().parents[1] / os.environ.get(
    "KEPLOY_ARTIFACT_DIR", "test-results/keploy-api-verified"
)
OUT.mkdir(parents=True, exist_ok=True)
items = []
covered = set()


def capture(name, method, path, status, headers=None, data=None):
    response = requests.request(
        method, BASE + path, headers=headers, json=data, timeout=20
    )
    assert response.status_code == status, (
        name,
        response.status_code,
        response.text[:200],
    )
    request = {
        "method": method,
        "url": BASE + path,
        "header": [
            {"key": key, "value": value} for key, value in (headers or {}).items()
        ],
    }
    if data is not None:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        request["body"] = {"mode": "raw", "raw": json.dumps(data)}
    items.append(
        {
            "name": name,
            "request": request,
            "response": [
                {
                    "name": name,
                    "originalRequest": request,
                    "code": status,
                    "status": response.reason,
                    "header": [
                        {"key": key.title(), "value": value}
                        for key, value in response.headers.items()
                    ],
                    "body": response.text,
                }
            ],
        }
    )
    covered.add((method.lower(), path.split("?")[0]))
    return response.json()


# Seed mutations before recording reads so replay starts from a settled fixture.
seed_payload = {
    "submission_id": "keploy-repair-opening-v1",
    "financial_year": "2022-23",
    "opening_date": "2022-04-01",
    "stock_items": [
        {
            "product_id": 28,
            "warehouse_id": 1,
            "quantity": "2",
            "unit_cost": "100",
            "opening_date": "2022-04-01",
        }
    ],
}
setup_login = requests.post(
    BASE + "/api/v1/auth/login",
    json={"username": "superadmin", "password": "Admin@1234"},
    timeout=20,
)
setup_login.raise_for_status()
setup_response = requests.post(
    BASE + "/api/v1/opening-balances/",
    json=seed_payload,
    headers={"Authorization": "Bearer " + setup_login.json()["access_token"]},
    timeout=20,
)
assert setup_response.status_code == 201, setup_response.text[:200]
capture("Health", "GET", "/health", 200)
for route in (
    "/auth/me",
    "/opening-balances/stock-template/csv",
    "/notifications/",
    "/notifications/settings",
    "/scheduled-reports/settings",
    "/backup/status",
    "/reports/pnl",
    "/journal/",
    "/invoices/",
    "/warehouses/",
):
    capture("Anonymous access denied " + route, "GET", "/api/v1" + route, 401)
capture("Malformed login rejected", "POST", "/api/v1/auth/login", 422, data={})
capture(
    "Unknown account rejected",
    "POST",
    "/api/v1/auth/login",
    401,
    data={
        "username": "nonexistent_repair_account",
        "password": "Synthetic-invalid-input",
    },
)

for role in ("super_admin", "admin", "accountant", "sales", "warehouse"):
    username = "superadmin" if role == "super_admin" else "repair_" + role
    password = "Admin@1234" if role == "super_admin" else "RepairPass@123"
    auth = requests.post(
        BASE + "/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    auth.raise_for_status()
    headers = {"Authorization": "Bearer " + auth.json()["access_token"]}
    capture(role + " current user", "GET", "/api/v1/auth/me", 200, headers)
    capture(
        role + " profit restriction",
        "GET",
        "/api/v1/reports/pnl",
        200 if role == "super_admin" else 403,
        headers,
    )
    if role == "super_admin":
        for path in (
            "/notifications/settings",
            "/scheduled-reports/settings",
            "/scheduled-reports/status",
            "/notifications/",
            "/backup/status",
            "/products/",
            "/warehouses/",
            "/reports/stock",
        ):
            capture("Repaired read " + path, "GET", "/api/v1" + path, 200, headers)
        payload = seed_payload
        first = capture(
            "Opening balance posting",
            "POST",
            "/api/v1/opening-balances/",
            201,
            headers,
            payload,
        )
        second = capture(
            "Opening balance idempotency",
            "POST",
            "/api/v1/opening-balances/",
            201,
            headers,
            payload,
        )
        assert first == second
    else:
        capture(
            role + " opening denied",
            "POST",
            "/api/v1/opening-balances/",
            403,
            headers,
            {"financial_year": "2026-27", "opening_date": "2026-04-01"},
        )

(OUT / "collection.json").write_text(
    json.dumps(
        {
            "info": {
                "name": "ERP isolated repair regression",
                "schema": "https://schema.getpostman.com/json/collection/v2.0.0/collection.json",
            },
            "item": items,
        },
        indent=2,
    ),
    encoding="utf-8",
)
(OUT / "keploy.yml").write_text(
    """version: api.keploy.io/v1beta1
name: erp-demo-repairs-local
test:
  globalNoise:
    global:
      header:
        Date: []
        Connection: []
""",
    encoding="utf-8",
)
schema = requests.get(BASE + "/openapi.json", timeout=20).json()
operations = [
    (method, path)
    for path, methods in schema["paths"].items()
    for method in methods
    if method in {"get", "post", "put", "patch", "delete"}
]
(OUT / "coverage.json").write_text(
    json.dumps(
        {
            "captured_requests": len(items),
            "total_api_operations": len(operations),
            "covered_operations": sorted(covered),
            "not_captured_operations": [
                entry for entry in operations if entry not in covered
            ],
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(
    f"Captured and asserted {len(items)} local API requests. Artifacts contain disposable test tokens; do not upload or commit them."
)
