import logging
import uuid
import hashlib
import json
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.constants import TASK_ANALYSIS
from src.repositories.job_repository import JobRepository
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.agents.analyzer.run import run_analyzer_agent
from src.agents.utils import generate_thread_id, get_task_id

logger = logging.getLogger(__name__)

async def re_analyze(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Force re-analysis for a candidate attached to a job.
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

    # Require job description
    if not job.get("raw_text") and not job.get("markdown_content"):
        raise HTTPException(
            status_code=400, 
            detail="Cannot analyze a job without a job description."
        )

    candidate_repo = CandidateRepository(db)
    # Verify candidate belongs to org
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Candidate does not belong to this organization")

    # Check if they are attached
    is_attached = False
    for attached in job.get("attached_candidates", []):
        if str(attached["id"]) == str(candidate_id):
            is_attached = True
            resume_id = uuid.UUID(attached["attached_resume_id"]) if attached.get("attached_resume_id") else None
            break
    
    if not is_attached:
        raise HTTPException(status_code=400, detail="Candidate is not attached to this job.")

    resume_repo = ResumeRepository(db)
    if not resume_id:
        # Fallback to latest resume if not specifically attached (though it should be)
        current_resume_obj = await resume_repo.get_original_resume_by_candidate_id(candidate_id)
        resume_id = current_resume_obj.id if current_resume_obj else None
    else:
        # Get specific resume
        from src.models.db_models import Resume
        res_result = await db.execute(select(Resume).where(Resume.id == resume_id))
        current_resume_obj = res_result.scalar_one_or_none()

    if not current_resume_obj:
        raise HTTPException(status_code=400, detail="No resume found for analysis.")

    # Get candidate notes and location
    candidate_notes = await candidate_repo.get_notes(candidate_id)
    candidate_location = candidate.location if hasattr(candidate, 'location') else None
    
    # Prepare additional candidate metadata for analyzer
    candidate_metadata = {
        "citizenship": candidate.citizenship,
        "linkedin_url": candidate.linkedin_url,
        "engagement_types": candidate.engagement_types,
        "work_preference": candidate.work_preference,
        "open_to_relocation": candidate.open_to_relocation
    }
    
    analysis_repo = AnalysisRepository(db)
    existing_analysis = await analysis_repo.get_analysis_for_candidate_job_resume(
        candidate_id=candidate_id,
        job_id=job_id,
        resume_id=resume_id
    )
    
    raw_jd = job.get("raw_text", "")
    details = job.get("details", {})
    
    jd_hash = hashlib.sha256(raw_jd.encode()).hexdigest() if raw_jd else None
    details_hash = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest() if details else None

    logger.info(f"Forcing re-analysis for candidate {candidate_id} and job {job_id} using resume {resume_id}")
    
    # Create a skeleton analysis record or update existing one
    skeleton_content = {"status": "processing", "message": "Analysis is being re-generated..."}
    
    if existing_analysis:
        await analysis_repo.update_analysis(
            analysis_id=uuid.UUID(str(existing_analysis["id"])),
            content=skeleton_content,
            jd_hash=jd_hash,
            details_hash=details_hash
        )
    else:
        await analysis_repo.create_analysis(
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
        task_type=TASK_ANALYSIS,
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
        candidate_notes=candidate_notes,
        candidate_location=candidate_location,
        candidate_metadata=candidate_metadata,
        org_id=org.id
    )

    return {
        "success": True,
        "message": "Re-analysis started"
    }
