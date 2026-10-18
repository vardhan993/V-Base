"""Billing & plans (prices are quoted in INR).

Plans gate capacity, never features. Changing a plan via the API is
self-serve bookkeeping (it records the chosen tier); wiring a real payment
gateway is deliberately left as its own integration step.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from nexus.api.deps import get_current_user
from nexus.database.models import Contact, Company, User
from nexus.core.db import get_session
from nexus.core.plans import PLANS, PLAN_ADMIN, is_valid_plan, plan_summary, plan_for_email, plan_record_cap

from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def record_count(session: AsyncSession, user: User) -> int:
    return (
        (await session.execute(select(func.count(Contact.id)).where(Contact.created_by_id == user.id))).scalar_one()
        + (await session.execute(select(func.count(Company.id)).where(Company.created_by_id == user.id))).scalar_one()
    )


async def enforce_record_quota(session: AsyncSession, user: User) -> None:
    """Block record creation once the account reaches its plan's capacity.

    Capacities are per-account record counts (contacts + companies). Admin
    plans are unlimited and always bypass the check.
    """
    cap = plan_record_cap(user.plan) if user.plan else None
    if not cap:
        return
    if await record_count(session, user) >= cap:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Plan limit reached: {PLANS[user.plan]['name']} allows {cap:,} records. "
                "Upgrade your plan in Settings to add more."
            ),
        )


@router.get("/billing/plans")
async def list_plans(current_user: User = Depends(get_current_user)):
    return {
        "current_plan": PLANS[current_user.plan]["name"] if current_user.plan in PLANS else current_user.plan,
        "current_plan_key": current_user.plan,
        "is_admin_plan": current_user.plan == PLAN_ADMIN,
        "plans": plan_summary(),
    }


@router.post("/billing/plan")
async def change_plan(
    body: dict,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    target = str(body.get("plan") or "").strip().lower()
    if not is_valid_plan(target):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown plan")
    if current_user.plan == PLAN_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin accounts are permanently unlimited and cannot switch plans",
        )
    current_user.plan = target
    await session.commit()
    return {
        "plan": target,
        "name": PLANS[target]["name"],
        "price_inr": PLANS[target]["price_inr"],
        "record_cap": PLANS[target]["record_cap"],
    }


def plan_for_email_public(email: str) -> str:  # re-exported for signup use
    return plan_for_email(email)
