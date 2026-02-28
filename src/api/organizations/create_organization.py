import logging
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.api.organizations.models import OrganizationCreate, OrganizationResponse

logger = logging.getLogger(__name__)

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
