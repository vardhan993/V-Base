"""Plan & billing metadata for V-Base.

Plans do not gate features — every plan has the full CRM. Plans differ only
by record capacity (contacts + companies). Prices are quoted in Indian
rupees (INR). Accounts created with an email on ``ADMIN_EMAILS`` are
permanent, unlimited, free-of-charge admin plans — the product owner's
account(s).
"""

from __future__ import annotations

import os
from typing import Any

PLAN_ADMIN = "admin"
PLAN_STARTER = "starter"
PLAN_GROWTH = "growth"
PLAN_SCALE = "scale"

_VALID_PLANS = {PLAN_ADMIN, PLAN_STARTER, PLAN_GROWTH, PLAN_SCALE}


def _admin_emails() -> set[str]:
    raw = os.environ.get("ADMIN_EMAILS", "chitralakeerthivardhan@gmail.com")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def plan_for_email(email: str) -> str:
    """The plan a new account starts on. Admin emails are always ADMIN (free)."""
    return PLAN_ADMIN if (email or "").strip().lower() in _admin_emails() else PLAN_STARTER


def plan_price_inr(plan: str) -> int:
    meta = PLANS.get(plan)
    return int(meta["price_inr"]) if meta else 0


PLANS: dict[str, dict[str, Any]] = {
    PLAN_ADMIN: {
        "key": PLAN_ADMIN,
        "name": "Admin",
        "price_inr": 0,
        "period": "forever",
        "record_cap": None,  # unlimited
        "tagline": "Product owner plan — everything, unlimited, no charge, forever.",
        "features": [
            "Unlimited contacts & companies",
            "Every CRM feature included",
            "Imports of any size",
            "Priority support",
        ],
    },
    PLAN_STARTER: {
        "key": PLAN_STARTER,
        "name": "Starter",
        "price_inr": 499,
        "period": "month",
        "record_cap": 5_000,
        "tagline": "For small teams getting organised.",
        "features": [
            "Up to 5,000 records (contacts + companies)",
            "Every CRM feature included",
            "CSV / XLSX imports",
            "Email support",
        ],
    },
    PLAN_GROWTH: {
        "key": PLAN_GROWTH,
        "name": "Growth",
        "price_inr": 1_499,
        "period": "month",
        "record_cap": 25_000,
        "tagline": "For growing pipelines — the most popular plan.",
        "features": [
            "Up to 25,000 records",
            "Bulk import (100k+ rows per file)",
            "Sequences & campaigns",
            "Priority email support",
        ],
    },
    PLAN_SCALE: {
        "key": PLAN_SCALE,
        "name": "Scale",
        "price_inr": 3_999,
        "period": "month",
        "record_cap": 200_000,
        "tagline": "For high-volume data teams.",
        "features": [
            "Up to 200,000 records",
            "Custom fields & advanced analytics",
            "Priority support",
        ],
    },
}


def is_valid_plan(plan: str | None) -> bool:
    return plan in _VALID_PLANS


def plan_summary() -> list[dict[str, Any]]:
    """Public list of purchasable plans (admin plan excluded)."""
    return [PLANS[k] for k in (PLAN_STARTER, PLAN_GROWTH, PLAN_SCALE)]


def plan_record_cap(plan: str) -> int | None:
    return PLANS.get(plan, {}).get("record_cap")
