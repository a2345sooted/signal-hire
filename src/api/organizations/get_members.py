import uuid
from typing import List
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.api.organizations.models import OrganizationMemberResponse

async def get_organization_members(
    org_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> List[OrganizationMemberResponse]:
    """
    Returns all members (users with roles) in the specified organization.
    The current user must be a member of the organization to view its members.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)
    
    # Check if user is a member of the organization
    user_role = await repo.get_user_role_in_org(user_id, org_id)
    if not user_role:
        raise HTTPException(status_code=403, detail="Not authorized to view this organization's members")

    members = await repo.get_organization_members(org_id)
    
    return [OrganizationMemberResponse.model_validate(member) for member in members]
