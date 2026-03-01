import uuid
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.api.organizations.models import OrganizationInviteCreate, OrganizationInviteResponse
from src.models.db_models import OrgRole
from src.services.email import email_service

async def invite_member(
    org_id: uuid.UUID,
    invite_data: OrganizationInviteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> OrganizationInviteResponse:
    """
    Invites a new member to the organization.
    Only OWNER or ADMIN roles can invite members.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)
    
    # Check if user has permission to invite (OWNER or ADMIN)
    user_role = await repo.get_user_role_in_org(user_id, org_id)
    if not user_role or user_role not in [OrgRole.OWNER, OrgRole.ADMIN]:
        raise HTTPException(
            status_code=403, 
            detail="Only organization owners and admins can invite new members"
        )

    # Create the invitation
    invite = await repo.create_organization_invite(
        org_id=org_id,
        email=invite_data.email,
        role=invite_data.role,
        inviter_id=user_id
    )
    
    # Get organization name for the email
    org = await repo.get_organization(org_id)
    
    # Get inviter's email
    from src.repositories.user_repository import UserRepository
    user_repo = UserRepository(db)
    inviter = await user_repo.get_user_by_id(user_id)
    inviter_email = inviter.email if inviter else "Someone"

    await db.commit()

    # Send invitation email (async, but we don't await it to avoid blocking the response)
    # Actually, for reliability it's better to await it or use a background task.
    # For now, let's await it.
    await email_service.send_organization_invite(
        to_email=invite_data.email,
        org_name=org.name if org else "an organization",
        inviter_email=inviter_email,
        invite_id=str(invite.id)
    )
    
    return OrganizationInviteResponse.model_validate(invite)
