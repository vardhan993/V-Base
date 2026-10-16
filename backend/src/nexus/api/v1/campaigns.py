from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.api.deps import get_current_user
from nexus.core.audit import record_activity
from nexus.core.db import get_session
from nexus.database import Campaign, CampaignRecipient, Contact, ContactEmail, ContactList, ListContact

router = APIRouter(tags=["campaigns"])


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _serialize(campaign: Campaign, counts: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "subject": campaign.subject,
        "body": campaign.body,
        "status": campaign.status,
        "list_id": campaign.list_id,
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "counts": counts or {},
    }


async def _counts(session: AsyncSession, campaign_id: int) -> dict[str, int]:
    rows = (await session.execute(
        select(CampaignRecipient.status, func.count()).where(CampaignRecipient.campaign_id == campaign_id).group_by(CampaignRecipient.status)
    )).all()
    return {s: n for s, n in rows}


async def _load_campaign(session: AsyncSession, campaign_id: int) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


@router.get("/campaigns")
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    base = select(Campaign).order_by(Campaign.created_at.desc())
    total = (await session.execute(select(func.count()).select_from(Campaign))).scalar() or 0
    rows = list((await session.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars())
    counts: dict[int, dict[str, int]] = {}
    if rows:
        recipient_rows = (await session.execute(
            select(CampaignRecipient.campaign_id, CampaignRecipient.status, func.count())
            .where(CampaignRecipient.campaign_id.in_([c.id for c in rows]))
            .group_by(CampaignRecipient.campaign_id, CampaignRecipient.status)
        )).all()
        for campaign_id, status_name, n in recipient_rows:
            counts.setdefault(campaign_id, {})[status_name] = n
    return {
        "items": [_serialize(c, counts.get(c.id)) for c in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    campaign = await _load_campaign(session, campaign_id)
    recipients = list((await session.execute(
        select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id).order_by(CampaignRecipient.email)
    )).scalars())
    return {
        **_serialize(campaign, await _counts(session, campaign_id)),
        "recipients": [
            {
                "id": r.id,
                "contact_id": r.contact_id,
                "email": r.email,
                "status": r.status,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "error": r.error,
            }
            for r in recipients
        ],
    }


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: dict[str, Any],
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    name = str(body.get("name") or "").strip()
    subject = str(body.get("subject") or "").strip()
    body_text = str(body.get("body") or "").strip()
    if not name or not subject or not body_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name, subject and body are required")

    list_id = body.get("list_id")
    if list_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="list_id is required")
    if isinstance(list_id, str):
        list_id = int(list_id)
    contact_list = await session.get(ContactList, list_id)
    if contact_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")

    campaign = Campaign(name=name, subject=subject, body=body_text, status="draft", list_id=list_id, created_by_id=current_user.id)
    session.add(campaign)
    await session.flush()

    # Freeze the recipients now: joins the list's contacts with their primary
    # email, applying suppression so a bad address can never enter the queue.
    rows = (await session.execute(
        select(Contact, ContactEmail)
        .join(ListContact, ListContact.contact_id == Contact.id)
        .join(ContactEmail, (ContactEmail.contact_id == Contact.id) & (ContactEmail.is_primary.is_(True)))
        .where(ListContact.list_id == list_id)
    )).all()

    added = suppressed = 0
    seen: set[str] = set()
    for contact, email in rows:
        addr = (email.email or "").strip().lower()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        status_name = "pending"
        if (email.status or "").lower() in ("unsubscribed", "bounced", "complained", "invalid") or (
            contact.email_status or ""
        ).lower() in ("unsubscribed", "bounced", "invalid"):
            status_name = "suppressed"
            suppressed += 1
        else:
            added += 1
        session.add(CampaignRecipient(campaign_id=campaign.id, contact_id=contact.id, email=addr, status=status_name))

    await record_activity(
        session,
        action="campaign_created",
        user_id=current_user.id,
        entity_type="campaigns",
        entity_id=campaign.id,
        description=f"Campaign '{name}' created with {added} recipients ({suppressed} suppressed)",
    )
    await session.commit()
    await session.refresh(campaign)
    return _serialize(campaign, {"pending": added, "suppressed": suppressed})


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Send now. Delivery is synchronous: one EmailMessage per recipient uses
    the existing outbound provider pipeline, and failures are recorded per
    recipient without aborting the batch."""
    from nexus.core.email import send_email

    campaign = await _load_campaign(session, campaign_id)
    if campaign.status not in ("draft", "scheduled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign is {campaign.status}; cannot send")

    recipients = list((await session.execute(
        select(CampaignRecipient).where(
            CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.status == "pending"
        )
    )).scalars())
    if not recipients:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending recipients")

    campaign.status = "sending"
    await session.commit()

    sent = failed = 0
    for recipient in recipients:
        try:
            result = await send_email(
                session,
                user_id=current_user.id,
                to=recipient.email,
                subject=campaign.subject,
                text=campaign.body,
                contact_id=recipient.contact_id,
            )
            if result.get("status") == "sent" or result.get("id"):
                recipient.status = "sent"
                recipient.sent_at = _utcnow()
                sent += 1
            else:
                recipient.status = "failed"
                recipient.error = str(result.get("error") or "unknown")[:500]
                failed += 1
        except Exception as exc:  # one bad address must not stop the batch
            recipient.status = "failed"
            recipient.error = str(exc)[:500]
            failed += 1

    campaign.status = "sent"
    campaign.sent_at = _utcnow()
    await record_activity(
        session,
        action="campaign_sent",
        user_id=current_user.id,
        entity_type="campaigns",
        entity_id=campaign.id,
        description=f"Campaign '{campaign.name}' sent to {sent} recipients ({failed} failed)",
    )
    await session.commit()
    return {"status": "sent", "sent": sent, "failed": failed}


@router.post("/campaigns/{campaign_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    campaign = await _load_campaign(session, campaign_id)
    if campaign.status in ("sent", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign already {campaign.status}")
    campaign.status = "cancelled"
    await session.commit()
    return {"status": "cancelled"}


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    session: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    campaign = await _load_campaign(session, campaign_id)
    if campaign.status == "sent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sent campaigns are kept for audit; cancel instead")
    await session.delete(campaign)
    await session.commit()
