import asyncio
import logging
import uuid
from typing import Annotated, Optional, List

from fastapi import Form, Depends, UploadFile, File, BackgroundTasks, Response, Request, HTTPException, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.agents.jd_processor.run import run_jd_agent
from src.agents.resume_processor.run import run_resume_agent, cancel_resume_agent
from src.api.ws.manager import manager
from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.services.storage import storage_service
from src.services.parser import extract_text_from_bytes

from datetime import datetime


logger = logging.getLogger(__name__)

class JobNoteCreate(BaseModel):
    content: str

class JobNoteResponse(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime
    user_id: uuid.UUID
    user_email: str

class JobCreate(BaseModel):
    title: str
    client_name: str
    raw_text: Optional[str] = None
    location: Optional[str] = None
    work_arrangement: Optional[str] = None  # in-office, hybrid, remote
    hybrid_days_per_week: Optional[int] = None
    pay_range_min: Optional[int] = None
    pay_range_max: Optional[int] = None
    pay_type: Optional[str] = None  # salary, hourly
    employment_type: Optional[str] = None  # fte, w2, contract
    offers_relocation: bool = False

class JobUpdate(BaseModel):
    title: Optional[str] = None
    client_name: Optional[str] = None
    raw_text: Optional[str] = None
    location: Optional[str] = None
    work_arrangement: Optional[str] = None
    hybrid_days_per_week: Optional[int] = None
    pay_range_min: Optional[int] = None
    pay_range_max: Optional[int] = None
    pay_type: Optional[str] = None
    employment_type: Optional[str] = None
    offers_relocation: Optional[bool] = None

class JobResponse(BaseModel):
    id: str
    org_id: Optional[str] = None
    title: str
    client_name: Optional[str] = None
    raw_text: Optional[str] = None
    markdown_text: Optional[str] = None
    location: Optional[str] = None
    work_arrangement: Optional[str] = None
    hybrid_days_per_week: Optional[int] = None
    pay_range_min: Optional[int] = None
    pay_range_max: Optional[int] = None
    pay: Optional[str] = None
    pay_type: Optional[str] = None
    employment_type: Optional[str] = None
    offers_relocation: bool = False
    created_at: Optional[str] = None
    resumes: List[dict] = []
    
    # New fields for list card
    status: str = "open"  # "open" or "closed"
    owner_email: str = "user@example.com"  # Stubbed
    resume_count: int = 0
    num_candidates: int = 0 # Stubbed
    tags: List[str] = [] # Stubbed
    top_candidates: List[dict] = []
    notes: List[JobNoteResponse] = []

    class Config:
        from_attributes = True
        # Keep job_title for backward compatibility if any
        populate_by_name = True

async def create_job(
    request: Request,
    body: JobCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Create a job directly in the database.
    Does NOT trigger the AI agent for now.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    # Only OWNER, ADMIN, or RECRUITER can create a job (all roles currently have this right)
    
    logger.info(f"Creating job: {body.title} for client: {body.client_name} for org: {org.name} ({org.id})")
    
    repo = JobRepository(db)
    
    # We use empty dict for structured_data as it's normally filled by agent
    # but the model now allows it to be null.
    job_id = await repo.create_job(
        title=body.title,
        client_name=body.client_name,
        raw_text=body.raw_text,
        org_id=org.id,
        location=body.location,
        work_arrangement=body.work_arrangement,
        hybrid_days_per_week=body.hybrid_days_per_week,
        pay_range_min=body.pay_range_min,
        pay_range_max=body.pay_range_max,
        pay_type=body.pay_type,
        employment_type=body.employment_type,
        offers_relocation=body.offers_relocation,
        structured_data={} 
    )
    
    await db.commit()
    
    return {
        "job_id": str(job_id)
    }

async def save_jd(
    request: Request,
    job_description: Annotated[str, Form(...)],
    background_tasks: BackgroundTasks,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Handle job description save requests.
    Kicks off the processor agent. Job record is created only after processing is complete.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")
    
    logger.info(f"Received save JD request for org: {org.slug}")
    
    # Generate a job_id for tracking and WebSocket channel, but don't save to DB yet
    job_id = uuid.uuid4()
    
    logger.info(f"Generated temporary job_id: {job_id}. Starting agent...")
    
    # We broadcast an initial message to the websocket if anyone is listening
    import json
    
    # Add a tiny delay to allow frontend to connect to WS before first broadcast
    async def initial_broadcast():
        await asyncio.sleep(0.5)
        logger.info(f"Sending initial broadcast for job_id: {job_id}")
        await manager.broadcast_to_job(
            json.dumps({"status": "Processing job description", "message": "Processing job description"}),
            str(job_id)
        )

    # Kick off the agent and initial broadcast in the background
    background_tasks.add_task(run_jd_agent, raw_text=job_description, job_id=job_id, org_id=org.id)
    background_tasks.add_task(initial_broadcast)
    
    return {
        "success": True,
        "message": "Job description processing started",
        "job_id": str(job_id)
    }

async def get_jobs(
    request: Request,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all jobs for the specified organization.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    logger.info(f"Fetching all jobs for org: {org.name} ({org.id})")
    repo = JobRepository(db)
    jobs = await repo.get_all_jobs(org_id=org.id)
    
    if jobs is None:
        logger.warning("JobRepository.get_all_jobs() returned None!")
        return []
    
    formatted_jobs = []
    for job in jobs:
        resumes = []
        if job.get("resumes"):
            for resume in job["resumes"]:
                resumes.append({
                    "id": resume.get("id"),
                    "original_filename": resume.get("name") or "Unknown",
                    "structured_data": {"rank": resume.get("rank")},
                    "analysis_id": resume.get("analysis_id")
                })
        
        # Sort resumes by rank to get top candidates
        sorted_resumes = sorted(resumes, key=lambda x: x["structured_data"].get("rank") or 0, reverse=True)
        top_candidates = sorted_resumes[:3] # Show top 3 candidates

        # Construct pay string
        pay_min = job.get("pay_range_min")
        pay_max = job.get("pay_range_max")
        pay_str = None
        if pay_min is not None and pay_max is not None:
            pay_str = f"${pay_min:,} - ${pay_max:,}"
        elif pay_min is not None:
            pay_str = f"${pay_min:,}+"
        elif pay_max is not None:
            pay_str = f"Up to ${pay_max:,}"

        formatted_jobs.append({
            "id": str(job["id"]),
            "title": job.get("title") or "Untitled Job",
            "client_name": job.get("client_name"),
            "markdown_text": job.get("markdown_content") or job.get("raw_text") or "",
            "raw_text": job.get("raw_text") or "",
            "location": job.get("location"),
            "work_arrangement": job.get("work_arrangement"),
            "hybrid_days_per_week": job.get("hybrid_days_per_week"),
            "pay_range_min": job.get("pay_range_min"),
            "pay_range_max": job.get("pay_range_max"),
            "pay": pay_str,
            "pay_type": job.get("pay_type"),
            "employment_type": job.get("employment_type"),
            "offers_relocation": job.get("offers_relocation") or False,
            "created_at": job.get("created_at"),
            "resumes": resumes,
            "resume_count": len(resumes),
            "num_candidates": len(resumes), # Stubbed but using actual count
            "tags": ["Engineering", "Urgent"], # Stubbed
            "top_candidates": top_candidates,
            "status": "open", # "open" or "closed"
            "owner_email": "user@example.com" # Stubbed
        })
    
    return formatted_jobs

async def upload_resume(
    request: Request,
    job_id: Annotated[uuid.UUID, Form(...)],
    x_org_slug: Annotated[str, Header()],
    resume: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle resume upload for a specific job.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    # Verify job belongs to this org
    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")
        
    logger.info(f"Received resume upload for job_id: {job_id}, filename: {resume.filename}, org: {org.slug}")
    
    # 1. Create a skeleton record in the database first to get a storage ID (resume_id)
    resume_repo = ResumeRepository(db)
    
    # Ensure filename is unique (optional here, but good for record keeping)
    unique_filename = await resume_repo.get_unique_filename(resume.filename)

    resume_id = await resume_repo.create_resume(
        original_filename=unique_filename,
        raw_text="",  # Empty initially, agent will fill it
        structured_data={"filename": unique_filename, "status": "uploading"},
        embedding=None,
        storage_key=None, # Will be set after upload
        job_id=job_id
    )
    
    # 2. Upload to storage using the resume_id as the directory name
    file_data = await resume.read()
    storage_key = await storage_service.upload_file_data(
        file_data, 
        resume.filename, 
        resume.content_type,
        dir_id=str(resume_id)
    )
    
    # 3. Update the resume record with the storage key
    await resume_repo.update_resume(
        resume_id=resume_id,
        storage_key=storage_key
    )
    
    await db.commit()
    
    logger.info(f"Resume skeleton saved with ID: {resume_id} and storage key: {storage_key}. Starting agent...")

    if background_tasks:
        background_tasks.add_task(
            run_resume_agent, 
            file_key=storage_key, 
            original_filename=unique_filename,
            job_id=job_id,
            resume_id=resume_id,
            org_id=org.id
        )
    
    return {
        "success": True,
        "message": "Resume uploaded and processing started",
        "resume_id": str(resume_id),
        "filename": resume.filename,
        "job_id": str(job_id)
    }

async def get_resume(resume_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a specific resume by ID.
    """
    logger.info(f"Fetching resume: {resume_id}")
    repo = ResumeRepository(db)
    resume = await repo.get_resume_by_id(resume_id)
    if not resume:
        return {"success": False, "message": "Resume not found"}
    return resume

async def get_resume_analysis(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve analysis for a specific resume by finding the candidate it belongs to.
    """
    logger.info(f"Fetching analysis for resume: {resume_id}")
    resume_repo = ResumeRepository(db)
    resume = await resume_repo.get_resume_by_id(resume_id)
    if not resume or not resume.get("candidate_id"):
        return {"success": False, "message": "Resume or candidate not found"}
    
    candidate_id = uuid.UUID(resume["candidate_id"])
    job_id = uuid.UUID(resume["job_id"])
    
    repo = AnalysisRepository(db)
    analysis = await repo.get_analysis_for_candidate_job(candidate_id, job_id)
    if not analysis:
        return {"success": False, "message": "Analysis not found"}
    return analysis

async def get_resume_pdf(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve the PDF file for a specific resume.
    """
    logger.info(f"Fetching PDF for resume: {resume_id}")
    repo = ResumeRepository(db)
    resume = await repo.get_resume_by_id(resume_id)
    
    if not resume or not resume.get("storage_key"):
        return Response(status_code=404, content="Resume PDF not found")
    
    try:
        file_response = await storage_service.get_file(resume["storage_key"])
        
        # Determine content type (default to application/pdf)
        filename = resume.get("filename", "resume.pdf").lower()
        content_type = "application/pdf"
        if filename.endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif filename.endswith(".doc"):
            content_type = "application/msword"
            
        return StreamingResponse(
            file_response, 
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{resume.get('filename', 'resume.pdf')}\""
            }
        )
    except Exception as e:
        logger.error(f"Error retrieving file from storage: {e}")
        return Response(status_code=500, content="Error retrieving file from storage")

async def get_analysis(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific analysis by ID, including candidate_id and job markdown.
    """
    logger.info(f"Fetching analysis: {analysis_id}")
    repo = AnalysisRepository(db)
    analysis_data = await repo.get_analysis_by_id(analysis_id)
    if not analysis_data:
        return {"success": False, "message": "Analysis not found"}
    
    candidate_repo = CandidateRepository(db)
    candidate = await candidate_repo.get_candidate_by_id(uuid.UUID(analysis_data["candidate_id"]))
    if not candidate:
        return {"success": False, "message": "Candidate not found for analysis"}
    
    # We might need to find a resume for this candidate/job to get more info (like email, filename)
    resume_repo = ResumeRepository(db)
    resumes = await resume_repo.get_resumes_by_job_id(uuid.UUID(analysis_data["job_id"]))
    # Filter by candidate_id
    candidate_resumes = [r for r in resumes if str(r.candidate_id) == analysis_data["candidate_id"]]
    resume = candidate_resumes[0] if candidate_resumes else None
    
    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(uuid.UUID(analysis_data["job_id"]))
    if not job:
         return {"success": False, "message": "Job not found for analysis"}
    
    return {
        "analysis": analysis_data["content"],
        "candidate_id": analysis_data["candidate_id"],
        "candidate_name": candidate.get("name") or "Unknown",
        "resume_id": str(resume.id) if resume else None,
        "resume_name": resume.original_filename if resume else "Unknown",
        "resume_email": (resume.structured_data or {}).get("contact", {}).get("email") if resume else "No email",
        "resume_structured_data": resume.structured_data if resume else {},
        "job_title": job.get("title") or "Untitled Job",
        "job_markdown": job.get("markdown_content") or job.get("raw_text") or ""
    }

async def stop_resume_processing(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Stop the running resume processing agent for a specific job.
    """
    logger.info(f"Stopping resume processing for job: {job_id}")
    cancelled = await cancel_resume_agent(job_id)
    
    # We always check for a skeleton resume even if cancelled is False, 
    # because the task might have finished but we still want to clean up if it's a skeleton.
    # However, the user specifically wants to delete it when THEY click stop.
    
    resume_repo = ResumeRepository(db)
    resumes = await resume_repo.get_resumes_by_job_id(job_id)
    
    # Sort by creation time (descending) and pick the most recent one that doesn't have an analysis
    skeleton_resume = None
    for r in sorted(resumes, key=lambda x: x.created_at, reverse=True):
        if not r.analyses:
            skeleton_resume = r
            break
    
    if skeleton_resume:
        logger.info(f"Deleting skeleton resume record: {skeleton_resume.id}")
        # Delete from storage first
        if skeleton_resume.storage_key:
            try:
                await storage_service.delete_file(skeleton_resume.storage_key)
            except Exception as e:
                logger.error(f"Failed to delete file from storage: {e}")
        
        # Delete from DB
        await resume_repo.delete_resume(skeleton_resume.id)
        
        await db.commit()
        logger.info(f"Cleanup completed for job {job_id}")

    # Also broadcast to the job channel so the UI can update immediately
    await manager.broadcast_to_job(
        "{\"status\": \"Stopped\", \"message\": \"Processing stopped by user\", \"completed\": false, \"failed\": false, \"stopped\": true}",
        str(job_id)
    )
    return {"success": True, "message": "Resume processing stopped and cleanup performed"}

async def delete_job_endpoint(
    request: Request,
    job_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific job and all its associated resumes/analyses.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    # Check if job belongs to org before deleting
    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
         return {"success": False, "message": "Job not found"}
    
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
         raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    
    logger.info(f"Deleting job: {job_id} for org: {org.slug}")
    
    # 1. Cancel any active agents for this job
    from ..agents.jd_processor.run import cancel_jd_agent
    jd_cancelled = await cancel_jd_agent(job_id)
    resume_cancelled = await cancel_resume_agent(job_id)
    logger.info(f"Agent cancellation status for job {job_id}: JD={jd_cancelled}, Resume={resume_cancelled}")
    
    # 2. Delete resumes and their files
    resume_repo = ResumeRepository(db)
    resumes = await resume_repo.get_resumes_by_job_id(job_id)
    logger.info(f"Found {len(resumes)} resumes to delete for job {job_id}")
    for resume in resumes:
        if resume.storage_key:
            try:
                await storage_service.delete_file(resume.storage_key)
            except Exception as e:
                logger.error(f"Failed to delete file for resume {resume.id}: {e}")
        await resume_repo.delete_resume(resume.id)
    
    # 3. Delete the job record
    job_repo = JobRepository(db)
    logger.info(f"Checking for job record {job_id} to delete")
    deleted = await job_repo.delete_job(job_id)
    await db.commit()
    logger.info(f"Job record {job_id} deletion status: {deleted}")
    
    # If it was deleted from DB or if JD agent was cancelled, we consider it a success
    if deleted or jd_cancelled:
        return {"success": True, "message": f"Job {job_id} cleanup performed"}
    return {"success": False, "message": "Job not found and no active processing"}

async def get_job(
    request: Request,
    job_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific job by ID for the specified organization.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    logger.info(f"Fetching job: {job_id} for org: {org.slug}")
    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
        return {"success": False, "message": "Job not found"}
    
    # Verify job belongs to this org
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")
    
    # Also fetch resumes for this job to match the format expected by frontend
    resumes = []
    from ..repositories.resume_repository import ResumeRepository
    resume_repo = ResumeRepository(db)
    job_resumes = await resume_repo.get_resumes_by_job_id(job_id)
    for resume in job_resumes:
        resumes.append({
            "id": str(resume.id),
            "original_filename": resume.original_filename,
            "structured_data": resume.structured_data,
            "analysis_id": str(resume.analyses[0].id) if resume.analyses else None,
            "analysis": {
                "id": str(resume.analyses[0].id),
                "content": resume.analyses[0].content,
                "created_at": resume.analyses[0].created_at.isoformat() if resume.analyses[0].created_at else None
            } if resume.analyses else None
        })
    
    # Use the JobResponse model to ensure all fields are returned
    job_data = {
        "id": str(job["id"]),
        "org_id": str(job["org_id"]) if job.get("org_id") else None,
        "title": job.get("title") or "Untitled Job",
        "client_name": job.get("client_name"),
        "markdown_text": job.get("markdown_content") or job.get("raw_text") or "",
        "raw_text": job.get("raw_text") or "",
        "location": job.get("location"),
        "work_arrangement": job.get("work_arrangement"),
        "hybrid_days_per_week": job.get("hybrid_days_per_week"),
        "pay_range_min": job.get("pay_range_min"),
        "pay_range_max": job.get("pay_range_max"),
        "pay_type": job.get("pay_type"),
        "employment_type": job.get("employment_type"),
        "offers_relocation": job.get("offers_relocation") or False,
        "created_at": job["created_at"].isoformat() if isinstance(job.get("created_at"), datetime) else job.get("created_at"),
        "resumes": resumes,
        "notes": job.get("notes") or [],
        "status": "open",
        "num_candidates": len(resumes),
        "tags": ["Engineering", "Urgent"],
        "resume_count": len(resumes)
    }
    
    # Construct pay string for consistency
    pay_min = job.get("pay_range_min")
    pay_max = job.get("pay_range_max")
    if pay_min is not None and pay_max is not None:
        job_data["pay"] = f"${pay_min:,} - ${pay_max:,}"
    elif pay_min is not None:
        job_data["pay"] = f"${pay_min:,}+"
    elif pay_max is not None:
        job_data["pay"] = f"Up to ${pay_max:,}"

    return JobResponse.model_validate(job_data)

async def patch_job_endpoint(
    request: Request,
    job_id: uuid.UUID,
    body: JobUpdate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Update a specific job by ID for the specified organization.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify job belongs to this org
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    logger.info(f"Patching job: {job_id} for org: {org.slug}")
    
    # We only update fields that were provided in the request body
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return {"success": True, "message": "No changes provided"}

    # Map 'title' in JobUpdate to 'title' in repo.update_job
    success = await repo.update_job(
        job_id=job_id,
        **update_data
    )
    
    if success:
        await db.commit()
        return {"success": True, "message": f"Job {job_id} updated successfully"}
    else:
        return {"success": False, "message": "Failed to update job"}

async def add_job_note_endpoint(
    request: Request,
    job_id: uuid.UUID,
    body: JobNoteCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to a job.
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

    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    note_id = await repo.add_job_note(
        job_id=job_id,
        user_id=user_id,
        content=body.content
    )
    
    await db.commit()
    
    return {
        "success": True,
        "note_id": str(note_id)
    }
