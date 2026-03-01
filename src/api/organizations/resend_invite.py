import uuid
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.api.organizations.models import OrganizationInviteResponse
from src.models.db_models import OrgRole
from src.services.email import email_service

async def resend_invite(
    org_id: uuid.UUID,
    invite_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> OrganizationInviteResponse:
    """
    Resends an invitation by resetting its expiration date.
    Only users with OWNER or ADMIN roles can resend invitations.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)

    # Authorization: Check if current user is OWNER or ADMIN
    user_role = await repo.get_user_role_in_org(user_id, org_id)
    if user_role not in [OrgRole.OWNER, OrgRole.ADMIN]:
        raise HTTPException(
            status_code=403, 
            detail="Only organization owners and admins can resend invitations"
        )

    invite = await repo.resend_organization_invite(org_id, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Get organization name for the email
    org = await repo.get_organization(org_id)
    
    # Get inviter's email
    from src.repositories.user_repository import UserRepository
    user_repo = UserRepository(db)
    inviter = await user_repo.get_user_by_id(user_id)
    inviter_email = inviter.email if inviter else "Someone"

    await db.commit()
    
    # Resend invitation email
    await email_service.send_organization_invite(
        to_email=invite.email,
        org_name=org.name if org else "an organization",
        inviter_email=inviter_email,
        invite_id=str(invite.id)
    )
    
    return OrganizationInviteResponse.model_validate(invite)
