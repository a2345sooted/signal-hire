import uuid
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from .models import CandidateResponse

async def get_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific candidate by ID.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    candidate_repo = CandidateRepository(db)
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    
    if not candidate_data:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    return {
        "success": True,
        "candidate": CandidateResponse.model_validate(candidate_data)
    }
