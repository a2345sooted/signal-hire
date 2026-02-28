import logging
import uuid
import os
from typing import Annotated
from fastapi import Depends, UploadFile, File, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.services.storage import storage_service
from src.services.parser import extract_text_from_bytes
from src.agents.resume_processor.run import run_resume_agent
import hashlib

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

async def upload_resume(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
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

    # Record in resumes table
    resume_repo = ResumeRepository(db)
    existing_resumes = await resume_repo.get_resumes_by_candidate_id(candidate_id)
    for res in existing_resumes:
        if res.original_filename == file.filename:
            logger.warning(f"Duplicate resume upload attempt for candidate {candidate_id}: {file.filename}")
            raise HTTPException(
                status_code=400,
                detail=f"A resume with the filename '{file.filename}' already exists for this candidate."
            )

    # 0. Extract text and check for exact content duplicates
    file_data = await file.read()
    raw_text = await extract_text_from_bytes(file_data, file.filename)
    
    if raw_text:
        text_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        existing_resume = await resume_repo.get_resume_by_hash(text_hash)
        
        if existing_resume:
            matching_filename = existing_resume.get("original_filename") or "an existing resume"
            logger.warning(f"Duplicate content detected for candidate {candidate_id}. Matches: {matching_filename}")
            raise HTTPException(
                status_code=409, 
                detail=f"This resume exactly matches another resume already in the system: {matching_filename}"
            )

    # 1. Create a skeleton record
    unique_filename = await resume_repo.get_unique_filename(file.filename)

    resume_id = await resume_repo.create_resume(
        original_filename=unique_filename,
        raw_text=raw_text or "",
        structured_data={},
        storage_key=None,
        candidate_id=candidate_id,
        is_current=True
    )

    # 2. Upload to storage using the resume_id as the directory name
    storage_key = await storage_service.upload_file_data(
        file_data, 
        file.filename, 
        file.content_type,
        dir_id=str(resume_id)
    )
    
    # 3. Update the resume record with the storage key
    await resume_repo.update_resume(
        resume_id=resume_id,
        storage_key=storage_key
    )
    
    await db.commit()
    
    logger.info(f"Resume skeleton saved with ID: {resume_id} and storage key: {storage_key}. Starting agent...")

    if background_tasks:
        background_tasks.add_task(
            run_resume_agent, 
            file_key=storage_key, 
            original_filename=unique_filename,
            candidate_id=candidate_id,
            resume_id=resume_id,
            org_id=org.id,
            raw_text=raw_text
        )
    
    return {
        "success": True,
        "message": "Resume uploaded and processing started",
        "resume_id": str(resume_id),
        "filename": file.filename,
        "candidate_id": str(candidate_id)
    }
