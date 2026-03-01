import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.processing_task_repository import ProcessingTaskRepository
from src.agents.optimizer.run import run_optimizer_agent

logger = logging.getLogger(__name__)

async def optimize_resume(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Triggers the resume optimization process for a specific job and candidate.
    Uses the candidate's current resume.
    """
    logger.info(f"Optimize resume requested for job_id: {job_id}, candidate_id: {candidate_id}, org: {x_org_slug}")
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        logger.warning(f"Optimization request failed: User not authenticated")
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        logger.warning(f"Optimization request failed: Organization '{x_org_slug}' not found")
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        logger.warning(f"Optimization request failed: User {user_id} does not belong to organization {org.id}")
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(job_id)
    if not job:
        logger.warning(f"Optimization request failed: Job {job_id} not found")
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.get("org_id")) != str(org.id):
        logger.warning(f"Optimization request failed: Job {job_id} (org: {job.get('org_id')}) does not belong to organization {org.id}")
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    candidate_repo = CandidateRepository(db)
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    if not candidate_data:
        logger.warning(f"Optimization request failed: Candidate {candidate_id} not found")
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get latest resume
    current_resume = await candidate_repo.get_latest_resume(candidate_id)
    if not current_resume:
        logger.warning(f"Optimization request failed: No current resume found for candidate {candidate_id}")
        raise HTTPException(status_code=400, detail="No current resume found for candidate. Please upload one first.")

    # Get latest analysis for context
    analysis_repo = AnalysisRepository(db)
    analysis = await analysis_repo.get_analysis_for_candidate_job_resume(
        candidate_id=candidate_id,
        job_id=job_id,
        resume_id=uuid.UUID(current_resume["id"])
    )
    
    if not analysis:
        # Fallback to any analysis for this candidate and job if resume-specific one is not found
        # This can happen if the resume ID was changed or if the analysis record doesn't have resume_id
        logger.info(f"No resume-specific analysis found for candidate {candidate_id}, job {job_id}, resume {current_resume['id']}. Checking for any analysis for this candidate and job.")
        analysis = await analysis_repo.get_analysis_for_candidate_job(
            candidate_id=candidate_id,
            job_id=job_id
        )

    if not analysis:
        # We probably should have an analysis before optimizing
        logger.warning(f"Optimization request failed: No match analysis found for job {job_id}, candidate {candidate_id}")
        raise HTTPException(status_code=400, detail="No match analysis found. Please attach candidate to job and wait for analysis to complete.")

    if analysis.get("content", {}).get("status") == "processing":
        logger.warning(f"Optimization request failed: Match analysis is still processing for job {job_id}, candidate {candidate_id}")
        raise HTTPException(status_code=400, detail="Match analysis is still processing. Please wait.")

    # Pre-register the optimizer task
    task_repo = ProcessingTaskRepository(db)
    # Using candidate_id as task_id for optimizer since it's per candidate-job
    # Actually, base_runner uses extract_uuid_from_thread_id which takes the last UUID.
    # thread_id will be optimizer_{job_id}_{candidate_id}
    # So task_id should be candidate_id.
    
    await task_repo.create_task(
        task_id=candidate_id,
        task_type="optimizer",
        job_id=job_id,
        candidate_id=candidate_id,
        resume_id=uuid.UUID(current_resume["id"]),
        status="starting"
    )
    await db.commit()

    logger.info(f"Triggering resume optimization for candidate {candidate_id} on job {job_id}")

    background_tasks.add_task(
        run_optimizer_agent,
        job_id=job_id,
        candidate_id=candidate_id,
        resume_id=uuid.UUID(current_resume["id"]),
        job_data=job,
        resume_data=current_resume,
        analysis_data=analysis,
        org_id=org.id
    )

    return {
        "success": True,
        "message": "Resume optimization started in the background."
    }
