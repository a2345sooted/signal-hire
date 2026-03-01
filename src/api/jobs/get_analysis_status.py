import logging
import uuid
from typing import Annotated, Optional
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.organization_repository import OrganizationRepository
from src.agents.analyzer.run import is_analysis_active

logger = logging.getLogger(__name__)

class AnalysisStatusResponse(BaseModel):
    success: bool
    status: str # starting, processing, completed, failed, pending
    job_id: uuid.UUID
    candidate_id: uuid.UUID
    error_message: Optional[str] = None

async def get_analysis_status(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    db: AsyncSession = Depends(get_db)
) -> AnalysisStatusResponse:
    """
    Check the status of analysis for a specific job and candidate.
    This is a lightweight endpoint for polling to avoid reloading the full analysis content.
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

    analysis_repo = AnalysisRepository(db)
    
    # Fallback to the latest analysis (likely for original resume)
    analysis = await analysis_repo.get_analysis_for_candidate_job(candidate_id, job_id)
    
    # Check if analysis exists and is completed
    if analysis:
        content = analysis.get("content", {})
        db_status = content.get("status")
        
        if db_status == "completed" or (db_status is None and content.get("score") is not None):
             return AnalysisStatusResponse(
                success=True,
                status="completed",
                job_id=job_id,
                candidate_id=candidate_id
            )
        
        if db_status == "processing":
            # Check if it's stuck (more than 10 minutes old)
            from datetime import datetime, timezone, timedelta
            created_at_str = analysis.get("created_at")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    
                    if (datetime.now(timezone.utc) - created_at) > timedelta(minutes=10):
                        logger.warning(f"Analysis {analysis.get('id')} is stuck in processing state for >10 mins.")
                    else:
                        return AnalysisStatusResponse(
                            success=True,
                            status="processing",
                            job_id=job_id,
                            candidate_id=candidate_id
                        )
                except (ValueError, TypeError):
                    return AnalysisStatusResponse(
                        success=True,
                        status="processing",
                        job_id=job_id,
                        candidate_id=candidate_id
                    )

    # Check for active tasks in DB
    from src.models.db_models import ProcessingTask
    from sqlalchemy import select
    task_stmt = (
        select(ProcessingTask)
        .where(ProcessingTask.candidate_id == candidate_id)
        .where(ProcessingTask.job_id == job_id)
        .where(ProcessingTask.task_type.in_(["analysis", "resume", "optimizer"]))
        .order_by(ProcessingTask.created_at.desc())
        .limit(1)
    )
    task_result = await db.execute(task_stmt)
    active_task = task_result.scalar_one_or_none()
    
    if active_task:
        if active_task.status in ["starting", "processing"]:
             return AnalysisStatusResponse(
                success=True,
                status=active_task.status,
                job_id=job_id,
                candidate_id=candidate_id
            )
        elif active_task.status == "failed":
             return AnalysisStatusResponse(
                success=False,
                status="failed",
                job_id=job_id,
                candidate_id=candidate_id,
                error_message=active_task.error_message
            )
        elif active_task.status == "completed":
             # If task is completed but we didn't find analysis above, it might be a race condition or partial failure
             # but we should probably trust the analysis find logic more for "completed" state.
             pass

    # Final fallback
    if await is_analysis_active(job_id, candidate_id):
        return AnalysisStatusResponse(
            success=True,
            status="processing",
            job_id=job_id,
            candidate_id=candidate_id
        )

    return AnalysisStatusResponse(
        success=False,
        status="pending",
        job_id=job_id,
        candidate_id=candidate_id
    )
