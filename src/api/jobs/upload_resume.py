import logging
import uuid
from typing import Annotated
from fastapi import Form, Depends, UploadFile, File, BackgroundTasks, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.resume_processor.run import run_resume_agent
from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.organization_repository import OrganizationRepository
from src.services.storage import storage_service
from src.services.parser import extract_text_from_bytes
import hashlib

logger = logging.getLogger(__name__)

async def upload_resume(
    request: Request,
    job_id: Annotated[uuid.UUID, Form(...)],
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    resume: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle resume upload for a specific job.
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

    # Verify job belongs to this org
    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")
        
    logger.info(f"Received resume upload for job_id: {job_id}, filename: {resume.filename}, org: {org.slug}")
    
    # 0. Extract text and check for exact duplicates
    file_data = await resume.read()
    raw_text = await extract_text_from_bytes(file_data, resume.filename)
    
    resume_repo = ResumeRepository(db)
    
    # Check for exact duplicate in ALL resumes
    if raw_text:
        text_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        existing_any = await resume_repo.get_resume_by_hash(text_hash)
        
        if existing_any:
            matching_filename = existing_any.get("original_filename") or "an existing resume"
            logger.warning(f"Duplicate resume detected. Matches: {matching_filename}")
            raise HTTPException(
                status_code=409, 
                detail=f"This resume exactly matches another resume already in the system: {matching_filename}"
            )

    # 1. Create a record in the database
    # In this endpoint, we don't have a candidate_id yet (it's created by the agent later).
    # But if it's an existing candidate, the agent (save_resume_node) should handle the overwrite.
    # However, for consistency with the candidate upload route, we should probably follow the same pattern
    # if we knew the candidate. But we don't.
    # So we'll let the agent handle the single-resume constraint during finalization.
    
    # Ensure filename is unique (optional here, but good for record keeping)
    unique_filename = await resume_repo.get_unique_filename(resume.filename)

    # Follow new convention for non-optimized resumes: jobs/:jobId/resumes/:resumeId
    # (Since this is a job-specific upload and candidate might not be created yet)
    resume_id = uuid.uuid4()
    storage_key = f"jobs/{job_id}/resumes/{resume_id}"

    await resume_repo.create_resume_with_id(
        resume_id=resume_id,
        original_filename=unique_filename,
        raw_text=raw_text or "",
        structured_data={},
        embedding=None,
        storage_key=storage_key,
        job_id=job_id
    )
    
    # 2. Upload to storage
    await storage_service.upload_file_data_with_key(
        file_data, 
        storage_key,
        resume.content_type
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
            job_id=job_id,
            resume_id=resume_id,
            status="starting"
        )
        await db.commit()

        background_tasks.add_task(
            run_resume_agent, 
            file_key=storage_key, 
            original_filename=unique_filename,
            job_id=job_id,
            resume_id=resume_id,
            org_id=org.id,
            raw_text=raw_text
        )
    
    return {
        "success": True,
        "message": "Resume uploaded and processing started",
        "resume_id": str(resume_id),
        "filename": resume.filename,
        "job_id": str(job_id)
    }
