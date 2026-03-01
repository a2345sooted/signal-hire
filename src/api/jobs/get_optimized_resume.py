import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import get_db
from src.repositories.resume_repository import ResumeRepository
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from src.agents.optimizer.run import is_optimizer_active

logger = logging.getLogger(__name__)

async def get_optimized_resume(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    db: AsyncSession = Depends(get_db)
):
    """
    Polling endpoint to retrieve the optimized resume for a specific job and candidate.
    Returns the status and the optimized resume if it's ready.
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

    logger.info(f"Polling optimized resume for job: {job_id}, candidate: {candidate_id}")
    
    # Check if a generated/optimized resume exists in the DB for this job/candidate combo
    repo = ResumeRepository(db)
    
    # We want the latest optimized resume for this candidate and job
    # ResumeRepository.get_resumes_by_candidate_id returns all resumes, but we need to filter
    all_resumes = await repo.get_resumes_by_candidate_id(candidate_id)
    
    optimized_resume = None
    if all_resumes:
        # Filter for optimized resumes matching the job_id
        matching = [
            r for r in all_resumes 
            if getattr(r, "is_optimized", False) and str(getattr(r, "job_id", "")) == str(job_id)
        ]
        if matching:
            # Sort by created_at descending to get the LATEST optimized resume
            from datetime import datetime, timezone
            matching.sort(key=lambda r: r.created_at if r.created_at else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            optimized_resume = matching[0] # Latest one

    if optimized_resume:
        # Generate signed URL if storage_key is present
        from src.services.storage import storage_service
        signed_url = None
        diff_signed_url = None
        storage_key = getattr(optimized_resume, "storage_key", None)
        if storage_key:
            try:
                if await storage_service.file_exists(storage_key):
                    signed_url = await storage_service.get_presigned_url(storage_key)
                else:
                    logger.warning(f"Optimized resume {optimized_resume.id} found in DB but missing from storage: {storage_key}.")
                    optimized_resume = None # Treat as not found if storage is missing
            except Exception as e:
                logger.error(f"Error checking storage for optimized resume {optimized_resume.id}: {e}")
                signed_url = None

        if optimized_resume:
            # Fetch diff markdown
            diff_markdown = None
            if hasattr(optimized_resume, "diff") and optimized_resume.diff:
                diff_markdown = optimized_resume.diff.get("markdown")
            
            logger.info(f"Picked optimized resume {optimized_resume.id} with diff_markdown length: {len(diff_markdown) if diff_markdown else 0}")
            if diff_markdown and "placeholder" in diff_markdown.lower():
                logger.warning(f"Optimized resume {optimized_resume.id} has PLACEHOLDER diff_markdown!")

    if optimized_resume:
        return {
            "success": True,
            "status": "completed",
            "resume": {
                "id": str(optimized_resume.id),
                "original_filename": optimized_resume.original_filename,
                "structured_data": optimized_resume.structured_data,
                "is_optimized": optimized_resume.is_optimized,
                "job_id": str(optimized_resume.job_id) if optimized_resume.job_id else None,
                "candidate_id": str(optimized_resume.candidate_id) if optimized_resume.candidate_id else None,
                "created_at": optimized_resume.created_at.isoformat() if optimized_resume.created_at else None,
                "signed_url": signed_url,
                "diff_markdown": diff_markdown
            }
        }

    # If no optimized resume found, check if it's still processing or failed
    from src.repositories.processing_task_repository import ProcessingTaskRepository
    from src.agents.utils import generate_thread_id, get_task_id
    from src.models.db_models import ProcessingTask

    # Generate the stable task_id used in optimize_resume.py
    thread_id = generate_thread_id("optimizer", job_id, str(candidate_id))
    task_id = get_task_id(thread_id)
    
    result = await db.execute(
        select(ProcessingTask)
        .where(ProcessingTask.id == task_id)
        .where(ProcessingTask.task_type == "optimizer")
        .where(ProcessingTask.job_id == job_id)
        .where(ProcessingTask.candidate_id == candidate_id)
    )
    task = result.scalar_one_or_none()
    
    if task:
        if task.status in ["starting", "processing"]:
            return {
                "success": True,
                "status": "processing",
                "message": "Optimization is still in progress."
            }
        elif task.status == "failed":
            error_detail = task.error_message or "An unknown error occurred during optimization."
            return {
                "success": False,
                "status": "failed",
                "message": f"Resume optimization failed: {error_detail}"
            }
    
    return {
        "success": False,
        "status": "not_started",
        "message": "No optimized resume found and no optimization process is active."
    }
