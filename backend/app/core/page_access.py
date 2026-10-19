"""Saved page permissions supplement, and never replace, existing role checks."""

import json

from fastapi import Depends, HTTPException, Request

from app.core.security import get_current_user, _role_str

PAGE_KEYS = frozenset(
    {
        "dashboard",
        "products",
        "purchase",
        "billing",
        "customers",
        "warehouse",
        "accounting",
        "gst",
        "reports",
        "bank",
        "security",
        "users",
        "settings",
    }
)


def has_page_access(user, *keys):
    if _role_str(user) in ("admin", "super_admin"):
        return True
    raw = getattr(user, "page_permissions", None)
    if raw is None:
        return True
    try:
        permissions = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return False
    return isinstance(permissions, list) and bool(set(keys) & set(permissions))


def require_page_access(request: Request, user=Depends(get_current_user)):
    path = request.url.path.removeprefix("/api/v1/").strip("/").split("/")
    root = path[0]
    # Master lists are shared by independently authorized transaction forms.
    shared = {
        "products": ("products", "billing", "purchase", "warehouse", "reports", "bank"),
        "categories": ("products", "billing", "purchase", "warehouse", "reports"),
        "warehouses": (
            "warehouse",
            "products",
            "billing",
            "purchase",
            "reports",
            "bank",
        ),
        "customers": ("customers", "billing", "reports", "accounting"),
        "vendors": ("purchase", "reports", "accounting"),
    }
    domains = {
        "products": "products",
        "categories": "products",
        "price-history": "products",
        "vendors": "purchase",
        "purchases": "purchase",
        "vendor-payments": "purchase",
        "customers": "customers",
        "invoices": "billing",
        "receipts": "billing",
        "warehouses": "warehouse",
        "stock-transfers": "warehouse",
        "stock-adjustments": "warehouse",
        "stock-writeoffs": "warehouse",
        "opening-balances": "warehouse",
        "cheques": "accounting",
        "cash-closing": "accounting",
        "expenses": "accounting",
        "tds": "accounting",
        "customer-ageing": "accounting",
        "journal": "accounting",
        "vendor-due-alerts": "accounting",
        "transporters": "gst",
        "vehicles": "gst",
        "einvoice": "gst",
        "ewaybill": "gst",
        "gstr1": "gst",
        "gstr2b": "gst",
        "gstr3b": "gst",
        "dashboard": "dashboard",
        "reports": "reports",
        "bank-stock-statement": "bank",
        "bank-reconciliation": "bank",
        "scheduled-reports": "bank",
        "backup": "bank",
        "users": "users",
        "users-admin": "users",
        "sessions": "security",
        "activity-log": "security",
        "login-history": "security",
        "settings": "settings",
        "dpdp": "settings",
        "config": "settings",
    }
    if root in {"auth", "2fa", "notifications"}:
        return user
    if (
        root == "settings"
        and len(path) > 1
        and path[1]
        in {
            "states",
            "company",
            "gst-rates",
            "tds-sections",
            "workflow-statuses",
            "workflow-transitions",
        }
        and request.method == "GET"
    ):
        return user
    keys = (domains.get(root, root),)
    if (
        request.method == "GET"
        and root in shared
        and (len(path) <= 2 and (len(path) == 1 or path[1].isdigit()))
    ):
        keys = shared[root]
    if (
        request.method == "GET"
        and root in {"products", "warehouses"}
        and len(path) == 3
        and path[1].isdigit()
        and path[2] == "stock"
    ):
        keys = shared[root]
    if not has_page_access(user, *keys):
        raise HTTPException(
            status_code=403, detail="Page access restricted by administrator"
        )
    return user
