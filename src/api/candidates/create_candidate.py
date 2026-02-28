import logging
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.api.candidates.models import CandidateCreate

logger = logging.getLogger(__name__)

async def create_candidate(
    request: Request,
    body: CandidateCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Handle candidate creation requests.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check if user has access to this organization
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    logger.info(f"Creating candidate '{body.name}' for organization '{x_org_slug}'")
    
    candidate_repo = CandidateRepository(db)
    # Use get_or_create logic if preferred, but here we'll just create or fail if unique constraints existed
    # For now, let's just create.
    candidate_id = await candidate_repo.create_candidate(
        name=body.name,
        email=body.email,
        org_id=org.id,
        phone=body.phone,
        location=body.location,
        citizenship=body.citizenship,
        linkedin_url=body.linkedin_url,
        engagement_types=body.engagement_types,
        work_preference=body.work_preference,
        open_to_relocation=body.open_to_relocation
    )
    
    await db.commit()
    
    # Fetch the created candidate to return it
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    
    return {
        "success": True,
        "candidate": candidate_data
    }
