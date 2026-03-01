import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.services.storage import storage_service
from src.agents.resume_processor.run import is_resume_processing_active

logger = logging.getLogger(__name__)

async def get_resumes(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all resumes for a specific candidate.
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
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    # Verify candidate exists and belongs to org
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Not authorized to access this candidate")

    resume_repo = ResumeRepository(db)
    resumes = await resume_repo.get_resumes_by_candidate_id(candidate_id)
    
    # Generate signed URLs for each resume
    formatted_resumes = []
    for r in resumes:
        signed_url = await storage_service.get_presigned_url(r.storage_key) if r.storage_key else None
        
        # Determine status: if structured_data is missing/empty, it's either processing or pending.
        # We also check the memory-based task registry.
        status = "ready"
        if not r.structured_data:
            status = "processing"
        elif is_resume_processing_active(resume_id=r.id):
            status = "processing"
            
        formatted_resumes.append({
            "id": str(r.id),
            "filename": r.original_filename,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "is_current": getattr(r, "is_current", False),
            "status": status,
            "signed_url": signed_url
        })
        
    return {
        "success": True,
        "resumes": formatted_resumes
    }
