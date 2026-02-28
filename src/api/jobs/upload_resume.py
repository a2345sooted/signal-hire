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

logger = logging.getLogger(__name__)

async def upload_resume(
    request: Request,
    job_id: Annotated[uuid.UUID, Form(...)],
    x_org_slug: Annotated[str, Header()],
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
    
    # 1. Create a skeleton record in the database first to get a storage ID (resume_id)
    resume_repo = ResumeRepository(db)
    
    # Ensure filename is unique (optional here, but good for record keeping)
    unique_filename = await resume_repo.get_unique_filename(resume.filename)

    resume_id = await resume_repo.create_resume(
        original_filename=unique_filename,
        raw_text="",  # Empty initially, agent will fill it
        structured_data={"filename": unique_filename, "status": "uploading"},
        embedding=None,
        storage_key=None, # Will be set after upload
        job_id=job_id
    )
    
    # 2. Upload to storage using the resume_id as the directory name
    file_data = await resume.read()
    storage_key = await storage_service.upload_file_data(
        file_data, 
        resume.filename, 
        resume.content_type,
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
            job_id=job_id,
            resume_id=resume_id,
            org_id=org.id
        )
    
    return {
        "success": True,
        "message": "Resume uploaded and processing started",
        "resume_id": str(resume_id),
        "filename": resume.filename,
        "job_id": str(job_id)
    }
