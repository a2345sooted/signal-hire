import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.agents.analyzer.run import is_analysis_active
from src.services.storage import storage_service

logger = logging.getLogger(__name__)

async def get_analysis(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve analysis for a specific job and candidate.
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

    logger.info(f"Fetching analysis for job: {job_id}, candidate: {candidate_id}")
    
    analysis_repo = AnalysisRepository(db)
    
    # Priority: If there's an optimized resume, we want its analysis
    from datetime import datetime, timezone
    repo = ResumeRepository(db)
    all_resumes = await repo.get_resumes_by_candidate_id(candidate_id)
    
    optimized_resume = None
    if all_resumes:
        matching = [r for r in all_resumes if getattr(r, "is_optimized", False) and str(getattr(r, "job_id", "")) == str(job_id)]
        if matching:
            matching.sort(key=lambda r: r.created_at if r.created_at else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            optimized_resume = matching[0]

    analysis = None
    if optimized_resume:
        analysis = await analysis_repo.get_analysis_for_candidate_job_resume(candidate_id, job_id, optimized_resume.id)
    
    if not analysis:
        # Fallback to the latest analysis (likely for original resume)
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
        # Check for active "resume" or "optimizer" tasks in the DB.
        from src.models.db_models import ProcessingTask
        from sqlalchemy import select
        task_stmt = (
            select(ProcessingTask)
            .where(ProcessingTask.candidate_id == candidate_id)
            .where(ProcessingTask.job_id == job_id)
            .where(ProcessingTask.task_type.in_(["resume", "optimizer"]))
            .where(ProcessingTask.status.in_(["starting", "processing"]))
        )
        task_result = await db.execute(task_stmt)
        active_task = task_result.scalar_one_or_none()
        
        if active_task:
            is_processing = True
            
    # Check for optimized resume
    # We already fetched resumes, let's reuse optimized_resume if found
    optimized_resume_info = None
    if optimized_resume:
        # Generate signed URL if storage_key is present
        signed_url = None
        storage_key = getattr(optimized_resume, "storage_key", None)
        if storage_key:
            try:
                # Check if the file actually exists in storage before claiming it's ready
                if await storage_service.file_exists(storage_key):
                    signed_url = await storage_service.get_presigned_url(storage_key)
                else:
                    logger.warning(f"Optimized resume {optimized_resume.id} found in DB but missing from storage: {storage_key}. Treating as null.")
                    optimized_resume = None
            except Exception as e:
                logger.error(f"Error checking storage for optimized resume {optimized_resume.id}: {e}")
                signed_url = None
        
        if optimized_resume:
            created_at = getattr(optimized_resume, "created_at", None)
            
            # Fetch parent resume's signed URL for the diff_signed_url field
            diff_markdown = None
            if hasattr(optimized_resume, "diff") and optimized_resume.diff:
                diff_markdown = optimized_resume.diff.get("markdown")
            
            logger.info(f"Picked optimized resume {optimized_resume.id} with diff_markdown length: {len(diff_markdown) if diff_markdown else 0}")
            if diff_markdown and "placeholder" in diff_markdown.lower():
                logger.warning(f"Optimized resume {optimized_resume.id} has PLACEHOLDER diff_markdown!")

            optimized_resume_info = {
                "id": str(getattr(optimized_resume, "id", "")),
                "status": "completed",
                "signed_url": signed_url,
                "diff_markdown": diff_markdown,
                "created_at": created_at.isoformat() if created_at and hasattr(created_at, "isoformat") else created_at
            }
    
    if not optimized_resume_info:
        # If no optimized resume found in DB, check if it's currently being generated or if it failed
        from src.models.db_models import ProcessingTask
        from sqlalchemy.future import select
        
        result = await db.execute(
            select(ProcessingTask)
            .where(ProcessingTask.candidate_id == candidate_id)
            .where(ProcessingTask.job_id == job_id)
            .where(ProcessingTask.task_type == "optimizer")
            .order_by(ProcessingTask.created_at.desc())
            .limit(1)
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
