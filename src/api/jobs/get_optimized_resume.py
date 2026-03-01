import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database import get_db
from src.repositories.resume_repository import ResumeRepository
from src.agents.optimizer.run import is_optimizer_active

logger = logging.getLogger(__name__)

async def get_optimized_resume(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Polling endpoint to retrieve the optimized resume for a specific job and candidate.
    Returns the status and the optimized resume if it's ready.
    """
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
            # Sort by created_at descending if available, or just pick the last one
            # Assuming the last one in the list or the one with the highest ID if sequential
            optimized_resume = matching[-1]

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
                "created_at": optimized_resume.created_at.isoformat() if optimized_resume.created_at else None
            }
        }

    # If no optimized resume found, check if it's still processing or failed
    from src.repositories.processing_task_repository import ProcessingTaskRepository
    task_repo = ProcessingTaskRepository(db)
    # Using candidate_id as task_id for optimizer since it's per candidate-job
    # (Matches what's done in optimize_resume.py:93)
    from sqlalchemy.future import select
    from src.models.db_models import ProcessingTask
    
    result = await db.execute(
        select(ProcessingTask)
        .where(ProcessingTask.id == candidate_id)
        .where(ProcessingTask.task_type == "optimizer")
        .where(ProcessingTask.job_id == job_id)
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
