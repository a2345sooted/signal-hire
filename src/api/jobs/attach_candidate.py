import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

async def attach_candidate(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Attach a candidate to a job.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    candidate_repo = CandidateRepository(db)
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    if not candidate_data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # In CandidateRepository, we don't have a direct way to check org_id easily without model
    # But get_candidate_by_id should probably have it. Let's check db_models.
    # Candidate table has org_id. Let's use it.
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Candidate does not belong to this organization")

    attachment_id = await job_repo.attach_candidate(
        job_id=job_id,
        candidate_id=candidate_id
    )
    
    await db.commit()
    
    return {
        "success": True,
        "attachment_id": str(attachment_id)
    }
