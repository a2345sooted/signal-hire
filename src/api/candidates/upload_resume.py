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
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
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
    existing_original = await resume_repo.get_original_resume_by_candidate_id(candidate_id)
    
    # 0. Extract text and check for exact content duplicates
    file_data = await file.read()
    raw_text = await extract_text_from_bytes(file_data, file.filename)
    
    if raw_text:
        text_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        
        # Check if it matches the current original resume exactly
        if existing_original and existing_original.raw_text_hash == text_hash:
             logger.warning(f"Exact same resume content uploaded for candidate {candidate_id}")
             raise HTTPException(
                status_code=409, 
                detail=f"This resume exactly matches the one already on file for this candidate."
            )
        
        # Check against ALL resumes in system (optional, but keep for now as per previous logic)
        existing_any = await resume_repo.get_resume_by_hash(text_hash)
        if existing_any and str(existing_any.get("candidate_id")) != str(candidate_id):
            matching_filename = existing_any.get("original_filename") or "an existing resume"
            logger.warning(f"Duplicate content detected for candidate {candidate_id}. Matches: {matching_filename}")
            raise HTTPException(
                status_code=409, 
                detail=f"This resume exactly matches another resume already in the system: {matching_filename}"
            )
    
    # If we have an existing original resume, we will delete it (and its storage) 
    # and replace it with the new one.
    if existing_original:
        logger.info(f"Overwriting existing resume {existing_original.id} for candidate {candidate_id}")
        # Delete from storage
        if existing_original.storage_key:
            try:
                await storage_service.delete_file(existing_original.storage_key)
            except:
                logger.warning(f"Failed to delete old resume storage: {existing_original.storage_key}")
        
        # Cancel any active tasks for old resume
        from src.agents.resume_processor.run import cancel_resume_agent
        await cancel_resume_agent(resume_id=existing_original.id)
        
        # Delete from DB
        await resume_repo.delete_resume(existing_original.id)
        await db.flush()

    # 1. Create a skeleton record
    unique_filename = await resume_repo.get_unique_filename(file.filename)

    # Follow new convention for non-optimized resumes: candidates/:candidateId/resumes/:resumeId
    # We pre-generate resume_id to use it in the storage key
    resume_id = uuid.uuid4()
    storage_key = f"candidates/{candidate_id}/resumes/{resume_id}"

    await resume_repo.create_resume_with_id(
        resume_id=resume_id,
        original_filename=unique_filename,
        raw_text=raw_text or "",
        structured_data={},
        storage_key=storage_key,
        candidate_id=candidate_id
    )

    # 2. Upload to storage using the full storage_key
    await storage_service.upload_file_data_with_key(
        file_data, 
        storage_key,
        file.content_type
    )
    
    await db.commit()
    
    logger.info(f"Resume skeleton saved with ID: {resume_id} and storage key: {storage_key}. Registering task and starting agent...")

    if background_tasks:
        # Pre-register the task in the database so that immediate status checks see 'processing'
        from src.repositories.processing_task_repository import ProcessingTaskRepository
        task_repo = ProcessingTaskRepository(db)
        await task_repo.create_task(
            task_id=resume_id, # For resume tasks, task_id is the resume_id
            task_type="resume",
            candidate_id=candidate_id,
            resume_id=resume_id,
            status="starting"
        )
        await db.commit()

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
