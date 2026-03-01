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
from src.agents.analyzer.run import run_analyzer_agent
from src.agents.utils import generate_thread_id, get_task_id

logger = logging.getLogger(__name__)

async def attach_candidate(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Attach a candidate to a job.
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

    # Require job description to be filled in
    if not job.get("raw_text") and not job.get("markdown_content"):
        raise HTTPException(
            status_code=400, 
            detail="Cannot attach candidate to a job without a job description. Please add a JD first."
        )

    candidate_repo = CandidateRepository(db)
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    if not candidate_data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # In CandidateRepository, we don't have a direct way to check org_id easily without model
    # But get_candidate_by_id should probably have it. Let's check db_models.
    # Candidate table has org_id. Let's use it.
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Candidate does not belong to this organization")

    # Trigger analysis if needed
    # If the candidate has resumes, pick the latest one if not already specified in the attachment
    # Now we only support ONE original resume, so get that one.
    resume_repo = ResumeRepository(db)
    current_resume_obj = await resume_repo.get_original_resume_by_candidate_id(candidate_id)
    resume_id = current_resume_obj.id if current_resume_obj else None

    # Update attachment with the resume_id (initially the original one)
    attachment_id = await job_repo.attach_candidate(
        job_id=job_id,
        candidate_id=candidate_id,
        resume_id=resume_id
    )
    
    if current_resume_obj:
        analysis_repo = AnalysisRepository(db)
        existing_analysis = await analysis_repo.get_analysis_for_candidate_job_resume(
            candidate_id=candidate_id,
            job_id=job_id,
            resume_id=resume_id
        )
        
        # Check if re-analysis is actually needed
        import hashlib
        import json
        
        raw_jd = job.get("raw_text", "")
        details = job.get("details", {})
        
        jd_hash = hashlib.sha256(raw_jd.encode()).hexdigest() if raw_jd else None
        details_hash = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest() if details else None

        needs_analysis = True
        if existing_analysis:
            # If JD hasn't changed, we can reuse this analysis
            if existing_analysis.get("jd_hash") == jd_hash and existing_analysis.get("details_hash") == details_hash:
                content = existing_analysis.get("content", {})
                if content.get("status") != "processing":
                    needs_analysis = False
                    logger.info(f"Analysis already exists and is valid for candidate {candidate_id}, job {job_id}, and resume {resume_id}. Skipping.")
        
        if needs_analysis:
            logger.info(f"Triggering analysis for candidate {candidate_id} and job {job_id} using resume {resume_id}")
            
            # Create a skeleton analysis record or update existing one
            skeleton_content = {"status": "processing", "message": "Analysis is being generated..."}
            
            if existing_analysis:
                await analysis_repo.update_analysis(
                    analysis_id=uuid.UUID(existing_analysis["id"]),
                    content=skeleton_content,
                    jd_hash=jd_hash,
                    details_hash=details_hash
                )
                analysis_id = uuid.UUID(existing_analysis["id"])
            else:
                analysis_id = await analysis_repo.create_analysis(
                    candidate_id=candidate_id,
                    job_id=job_id,
                    content=skeleton_content,
                    resume_id=resume_id,
                    jd_hash=jd_hash,
                    details_hash=details_hash
                )
            
            # Pre-register the task in the database
            from src.repositories.processing_task_repository import ProcessingTaskRepository
            task_repo = ProcessingTaskRepository(db)
            
            # Use stable task_id derived from thread_id
            thread_id = generate_thread_id("analysis", job_id, str(candidate_id))
            task_id = get_task_id(thread_id)
            
            await task_repo.create_task(
                task_id=task_id,
                task_type="analysis",
                job_id=job_id,
                candidate_id=candidate_id,
                resume_id=resume_id,
                status="starting"
            )
            await db.commit()

            background_tasks.add_task(
                run_analyzer_agent,
                job_id=job_id,
                candidate_id=candidate_id,
                job_data=job,
                resume_data={
                    "raw_text": current_resume_obj.raw_text,
                    "structured_data": current_resume_obj.structured_data,
                    "resume_id": str(resume_id)
                },
                org_id=org.id
            )
    else:
        logger.warning(f"No resume found for candidate {candidate_id}. Skipping analysis.")

    await db.commit()
    
    message = "Candidate attached to job"
    if current_resume_obj:
        if needs_analysis:
            message += " and analysis started"
        else:
            message += " and existing analysis reused"
    else:
        message += " (no resume found for analysis)"
    
    return {
        "success": True,
        "message": message,
        "attachment_id": str(attachment_id)
    }
