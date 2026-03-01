import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.analysis_repository import AnalysisRepository

logger = logging.getLogger(__name__)

async def delete_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific candidate.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    repo = CandidateRepository(db)
    candidate = await repo.get_candidate_by_id(candidate_id)
    if not candidate:
         return {"success": False, "message": "Candidate not found"}
    
    # Verify candidate belongs to org before deleting
    # Based on models, Candidate has org_id, but repository's get_candidate_by_id doesn't return org_id.
    # I should check if it exists in the raw object or if the repo needs update.
    # Looking at src/repositories/candidate_repository.py's get_candidate_by_id, it returns:
    # { "id": str(candidate.id), "name": candidate.name, "email": candidate.email, ... }
    # but not org_id.

    # Fetching raw candidate for org_id check
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    raw_candidate = result.scalar_one_or_none()

    if not raw_candidate:
         return {"success": False, "message": "Candidate not found"}

    if raw_candidate.org_id and str(raw_candidate.org_id) != str(org.id):
         raise HTTPException(status_code=403, detail="Not authorized to delete this candidate")
    
    logger.info(f"Deleting candidate: {candidate_id} for org: {org.slug}")
    
    # 1. Remove all analyses for this candidate
    analysis_repo = AnalysisRepository(db)
    await analysis_repo.delete_analyses_by_candidate_id(candidate_id)
    
    # 2. Delete the candidate record
    deleted = await repo.delete_candidate(candidate_id)
    await db.commit()
    
    if deleted:
        return {"success": True, "message": f"Candidate {candidate_id} deleted"}
    return {"success": False, "message": "Candidate not found"}
