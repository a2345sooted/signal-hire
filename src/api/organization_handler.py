import logging
from typing import Annotated, List
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
import uuid

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    slug: str

class OrganizationCreate(BaseModel):
    name: str

async def create_organization(
    request: Request,
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle organization creation requests.
    Assigns the current authenticated user as OWNER.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        # This shouldn't happen due to AuthMiddleware, but being safe
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User not authenticated")

    name = body.name
    logger.info(f"Creating organization '{name}' for user {user_id}")
    
    repo = OrganizationRepository(db)
    org = await repo.create_organization(name=name, user_id=user_id)
    await db.commit()

    return {
        "success": True,
        "organization": OrganizationResponse.model_validate(org)
    }

async def get_my_organizations(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> List[OrganizationResponse]:
    """
    Returns all organizations the current user belongs to.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)
    orgs = await repo.get_user_organizations(user_id)
    
    return [OrganizationResponse.model_validate(org) for org in orgs]
