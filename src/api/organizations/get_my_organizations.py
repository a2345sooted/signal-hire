from typing import List
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.api.organizations.models import OrganizationResponse

async def get_my_organizations(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> List[OrganizationResponse]:
    """
    Returns all organizations the current user belongs to.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)
    orgs = await repo.get_user_organizations(user_id)
    
    return [OrganizationResponse.model_validate(org) for org in orgs]
