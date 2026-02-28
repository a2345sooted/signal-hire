import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.resume_processor.run import cancel_resume_agent
from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.organization_repository import OrganizationRepository
from src.services.storage import storage_service

logger = logging.getLogger(__name__)

async def delete_job(
    request: Request,
    job_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific job and all its associated resumes/analyses.
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

    # Check if job belongs to org before deleting
    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
         return {"success": False, "message": "Job not found"}
    
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
         raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    
    logger.info(f"Deleting job: {job_id} for org: {org.slug}")
    
    # 1. Cancel any active agents for this job
    from src.agents.jd_processor.run import cancel_jd_agent
    jd_cancelled = await cancel_jd_agent(job_id)
    resume_cancelled = await cancel_resume_agent(job_id)
    logger.info(f"Agent cancellation status for job {job_id}: JD={jd_cancelled}, Resume={resume_cancelled}")
    
    # 2. Delete resumes and their files
    resume_repo = ResumeRepository(db)
    resumes = await resume_repo.get_resumes_by_job_id(job_id)
    logger.info(f"Found {len(resumes)} resumes to delete for job {job_id}")
    for resume in resumes:
        if resume.storage_key:
            try:
                await storage_service.delete_file(resume.storage_key)
            except Exception as e:
                logger.error(f"Failed to delete file for resume {resume.id}: {e}")
        await resume_repo.delete_resume(resume.id)
    
    # 3. Delete the job record
    job_repo = JobRepository(db)
    logger.info(f"Checking for job record {job_id} to delete")
    deleted = await job_repo.delete_job(job_id)
    await db.commit()
    logger.info(f"Job record {job_id} deletion status: {deleted}")
    
    # If it was deleted from DB or if JD agent was cancelled, we consider it a success
    if deleted or jd_cancelled:
        return {"success": True, "message": f"Job {job_id} cleanup performed"}
    return {"success": False, "message": "Job not found and no active processing"}
