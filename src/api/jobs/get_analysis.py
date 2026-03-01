import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.candidate_repository import CandidateRepository
from src.agents.analyzer.run import is_analysis_active
from src.services.storage import storage_service

logger = logging.getLogger(__name__)

async def get_analysis(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve analysis for a specific job and candidate.
    """
    logger.info(f"Fetching analysis for job: {job_id}, candidate: {candidate_id}")
    
    analysis_repo = AnalysisRepository(db)
    analysis = await analysis_repo.get_analysis_for_candidate_job(candidate_id, job_id)
    
    # Check if analysis is missing OR in a processing state
    is_processing = False
    
    # 1. Check if specific analysis is processing in DB
    if analysis and analysis.get("content", {}).get("status") == "processing":
        # Check if it's stuck (more than 10 minutes old)
        from datetime import datetime, timezone, timedelta
        created_at_str = analysis.get("created_at")
        if created_at_str:
            try:
                created_at = datetime.fromisoformat(created_at_str)
                # Ensure it's offset-aware for comparison
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                if (datetime.now(timezone.utc) - created_at) > timedelta(minutes=10):
                    logger.warning(f"Analysis {analysis.get('id')} is stuck in processing state for >10 mins, ignoring.")
                    is_processing = False
                else:
                    is_processing = True
            except (ValueError, TypeError):
                is_processing = True
        else:
            is_processing = True

    # 2. If no DB record or if it's explicitly 'processing', we check memory tasks
    if not is_processing and not analysis:
        if await is_analysis_active(job_id, candidate_id):
            is_processing = True

    # 3. Check if optimizer for THIS job is processing
    # Note: We only care about optimizer processing if we don't have an analysis yet
    if not is_processing and not analysis:
        from src.agents.optimizer.run import is_optimizer_active
        if await is_optimizer_active(job_id, candidate_id):
            is_processing = True

    # 4. Fallback: If no analysis yet, but resume is processing, we consider it processing
    if not analysis and not is_processing:
        # Check for active "resume" tasks in the DB.
        from src.models.db_models import ProcessingTask
        from sqlalchemy import select
        task_stmt = (
            select(ProcessingTask)
            .where(ProcessingTask.candidate_id == candidate_id)
            .where(ProcessingTask.task_type == "resume")
            .where(ProcessingTask.status.in_(["starting", "processing"]))
        )
        task_result = await db.execute(task_stmt)
        active_resume_task = task_result.scalar_one_or_none()
        
        if active_resume_task:
            # Only show "processing" if this is the first/only resume for the candidate
            from src.models.db_models import Resume
            res_count_stmt = select(Resume.id).where(Resume.candidate_id == candidate_id)
            res_count_result = await db.execute(res_count_stmt)
            if len(res_count_result.scalars().all()) <= 1:
                is_processing = True
            
    # Check for optimized resume
    repo = ResumeRepository(db)
    all_resumes = await repo.get_resumes_by_candidate_id(candidate_id)
    
    optimized_resume_info = None
    if all_resumes:
        # Filter for optimized resumes matching the job_id
        matching = [
            r for r in all_resumes 
            if getattr(r, "is_optimized", False) and str(getattr(r, "job_id", "")) == str(job_id)
        ]
        if matching:
            # Sort by created_at descending if available, or just pick the last one
            optimized_resume = matching[-1]
            
            # Generate signed URL if storage_key is present
            signed_url = None
            storage_key = getattr(optimized_resume, "storage_key", None)
            if storage_key:
                signed_url = await storage_service.get_presigned_url(storage_key)
            
            created_at = getattr(optimized_resume, "created_at", None)
            optimized_resume_info = {
                "id": str(getattr(optimized_resume, "id", "")),
                "status": "completed",
                "signed_url": signed_url,
                "created_at": created_at.isoformat() if created_at and hasattr(created_at, "isoformat") else created_at
            }
    
    if not optimized_resume_info:
        # If no optimized resume found in DB, check if it's currently being generated or if it failed
        from src.models.db_models import ProcessingTask
        from sqlalchemy.future import select
        
        result = await db.execute(
            select(ProcessingTask)
            .where(ProcessingTask.id == candidate_id)
            .where(ProcessingTask.task_type == "optimizer")
            .where(ProcessingTask.job_id == job_id)
        )
        task = result.scalar_one_or_none()
        
        if task:
            if task.status in ["starting", "processing"]:
                optimized_resume_info = {
                    "status": "processing"
                }
            elif task.status == "failed":
                optimized_resume_info = {
                    "status": "failed",
                    "error_message": task.error_message or "Unknown error"
                }
            else:
                optimized_resume_info = {
                    "status": "null"
                }
        else:
            optimized_resume_info = {
                "status": "null"
            }

    # If no optimized resume found or status is "null", don't include it in the response
    final_optimized_info = None
    if optimized_resume_info and optimized_resume_info.get("status") != "null":
        final_optimized_info = optimized_resume_info

    if is_processing:
        response = {
            "success": True,
            "status": "processing",
            "analysis": "SIGNAL_PROCESSING",
        }
        if final_optimized_info:
            response["optimized_resume"] = final_optimized_info
        return response
        
    if not analysis:
        response = {
            "success": False,
            "message": "Analysis not found",
            "status": "pending",
        }
        if final_optimized_info:
            response["optimized_resume"] = final_optimized_info
        return response
    
    response = {
        "success": True,
        "analysis": analysis.get("content", {}),
        "candidate_id": str(candidate_id),
        "job_id": str(job_id),
        "status": "completed",
    }
    if final_optimized_info:
        response["optimized_resume"] = final_optimized_info
    return response
