import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.agents.analyzer.run import run_analyzer_agent

logger = logging.getLogger(__name__)

class ChangeResumeRequest(BaseModel):
    resume_id: uuid.UUID

async def change_attachment_resume(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: ChangeResumeRequest,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Change the resume for a specific job attachment and trigger a new analysis.
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

    # Verify the new resume exists and belongs to the candidate
    resume_repo = ResumeRepository(db)
    resume = await resume_repo.get_resume_by_id(body.resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if str(resume.get("candidate_id")) != str(candidate_id):
        raise HTTPException(status_code=400, detail="Resume does not belong to this candidate")

    # Update the attachment with the new resume_id
    attachment_id = await job_repo.attach_candidate(
        job_id=job_id,
        candidate_id=candidate_id,
        resume_id=body.resume_id
    )
    
    # Trigger analysis with the new resume
    analysis_repo = AnalysisRepository(db)
    resume_id = body.resume_id
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
        # If JD and resume are the same, we check if it's already done
        if existing_analysis.get("jd_hash") == jd_hash and existing_analysis.get("details_hash") == details_hash:
            content = existing_analysis.get("content", {})
            if content.get("status") != "processing":
                needs_analysis = False
                logger.info(f"Analysis already exists and is valid for candidate {candidate_id}, job {job_id}, and NEW resume {resume_id}. Skipping.")
    
    if needs_analysis:
        logger.info(f"Triggering analysis for candidate {candidate_id} and job {job_id} using NEW resume {resume_id}")
        
        # Create a skeleton analysis record or update existing one
        skeleton_content = {"status": "processing", "message": "New resume attached. Re-analyzing..."}
        
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
        await task_repo.create_task(
            task_id=analysis_id,
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
                "raw_text": resume["raw_text"],
                "structured_data": resume["structured_data"],
                "resume_id": str(resume_id)
            },
            org_id=org.id
        )
    
    await db.commit()
    
    message = "Resume updated for attachment"
    if needs_analysis:
        message += " and analysis started"
    else:
        message += " and existing analysis reused"
    
    return {
        "success": True,
        "message": message,
        "resume_id": str(resume_id)
    }
