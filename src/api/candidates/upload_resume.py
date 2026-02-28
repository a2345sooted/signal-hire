import logging
import uuid
import os
from typing import Annotated
from fastapi import Depends, UploadFile, File, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.services.storage import storage_service

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

async def upload_resume(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a resume for a specific candidate.
    Path: {candidate_id}/resumes/{original_filename}
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

    candidate_repo = CandidateRepository(db)
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    if not candidate_data:
        raise HTTPException(status_code=404, detail="Candidate not found")
    
    # We should verify candidate belongs to org if Candidate model has org_id (it does)
    # But get_candidate_by_id returns a dict, let's verify if org_id is in there or we need the model.
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Candidate does not belong to this organization")

    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"File type not allowed. Please upload {', '.join(ALLOWED_EXTENSIONS)}"
        )

    logger.info(f"Uploading resume for candidate {candidate_id}: {file.filename}")

    # Upload to S3 with path: {candidate_id}/resumes/{filename}
    file_data = await file.read()
    dir_path = f"{candidate_id}/resumes"
    storage_key = await storage_service.upload_file_data(
        file_data,
        file.filename,
        file.content_type,
        dir_id=dir_path
    )

    # Record in resumes table
    resume_repo = ResumeRepository(db)
    resume_id = await resume_repo.create_resume(
        original_filename=file.filename,
        raw_text="", # Will be filled by agent if we trigger it, but for now we just upload
        structured_data={"status": "uploaded"},
        storage_key=storage_key,
        candidate_id=candidate_id
    )

    await db.commit()

    return {
        "success": True,
        "message": "Resume uploaded successfully",
        "resume_id": str(resume_id)
    }
