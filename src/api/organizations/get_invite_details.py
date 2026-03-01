import uuid
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.api.organizations.models import OrganizationInviteDetailResponse
from src.models.db_models import OrganizationInvite, Organization

async def get_invite_details(
    invite_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> OrganizationInviteDetailResponse:
    """
    Returns the details of an invitation.
    This is a public endpoint used to show info before accepting.
    """
    # Fetch invite with organization and inviter info
    stmt = (
        select(OrganizationInvite)
        .options(
            joinedload(OrganizationInvite.organization),
            joinedload(OrganizationInvite.inviter)
        )
        .where(OrganizationInvite.id == invite_id)
    )
    result = await db.execute(stmt)
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    # Check if expired
    from datetime import datetime, timezone
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invitation has expired")

    if invite.accepted_at:
        raise HTTPException(status_code=400, detail="Invitation has already been accepted")

    return OrganizationInviteDetailResponse(
        id=invite.id,
        org_id=invite.org_id,
        org_name=invite.organization.name,
        email=invite.email,
        role=invite.role,
        inviter_email=invite.inviter.email if invite.inviter else None,
        expires_at=invite.expires_at
    )
