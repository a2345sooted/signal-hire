import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.services.storage import storage_service
from src.agents.resume_processor.run import cancel_resume_agent
from src.agents.analyzer.run import cancel_analyzer_agent
from src.agents.optimizer.run import cancel_optimizer_agent

logger = logging.getLogger(__name__)

async def detach_candidate(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Detach a candidate from a job.
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

    # 1. Cancel any active tasks in memory for this combination
    # Cancel original resume analysis
    await cancel_analyzer_agent(job_id=job_id, candidate_id=candidate_id)
    # Cancel optimizer task
    await cancel_optimizer_agent(job_id=job_id, candidate_id=candidate_id)
    # Cancel optimized resume analysis (which uses f"{candidate_id}_opt" as thread seed)
    from src.agents.utils import generate_thread_id
    from src.agents.analyzer.run import _active_analysis_tasks
    from src.agents.base_runner import cancel_agent_task
    opt_analysis_thread_id = generate_thread_id("analysis", job_id, f"{candidate_id}_opt")
    await cancel_agent_task(opt_analysis_thread_id, _active_analysis_tasks, "ANALYZER_RUN_OPT")

    # 2. Find optimized resumes to clean up storage
    resume_repo = ResumeRepository(db)
    all_resumes = await resume_repo.get_resumes_by_candidate_id(candidate_id)
    optimized_resumes = [
        r for r in all_resumes 
        if getattr(r, "is_optimized", False) and getattr(r, "job_id", None) == job_id
    ]

    for res in optimized_resumes:
        # Delete from storage
        if res.storage_key:
            try:
                await storage_service.delete_file(res.storage_key)
                logger.info(f"Deleted optimized resume file {res.storage_key} for candidate {candidate_id}")
            except Exception as e:
                logger.error(f"Failed to delete file {res.storage_key} from S3: {e}")

        # Cancel any active tasks in memory specifically linked to this resume ID (if any)
        await cancel_resume_agent(job_id=job_id, resume_id=res.id)
        await cancel_analyzer_agent(job_id=job_id, candidate_id=candidate_id, resume_id=res.id)
        await cancel_optimizer_agent(job_id=job_id, candidate_id=candidate_id, resume_id=res.id)

    # 3. Mark all active processing tasks for this job/candidate as cancelled in DB
    from src.repositories.processing_task_repository import ProcessingTaskRepository
    from src.models.db_models import ProcessingTask
    from sqlalchemy import update
    
    await db.execute(
        update(ProcessingTask)
        .where(ProcessingTask.job_id == job_id)
        .where(ProcessingTask.candidate_id == candidate_id)
        .where(ProcessingTask.status.in_(["starting", "processing"]))
        .values(status="cancelled", updated_at=datetime.now(timezone.utc))
    )

    success = await job_repo.detach_candidate(
        job_id=job_id,
        candidate_id=candidate_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Attachment not found")
        
    # 3. Remove any analyses for this combination
    analysis_repo = AnalysisRepository(db)
    await analysis_repo.delete_analyses_for_candidate_job(
        candidate_id=candidate_id,
        job_id=job_id
    )
    
    await db.commit()
    
    return {
        "success": True,
        "message": f"Candidate {candidate_id} detached from job {job_id}"
    }
