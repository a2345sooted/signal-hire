import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import Form, Depends, UploadFile, File, BackgroundTasks, Response, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.jd_processor.run import run_jd_agent
from src.agents.resume_processor.run import run_resume_agent, cancel_resume_agent
from src.api.ws.manager import manager
from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.candidate_repository import CandidateRepository
from src.services.storage import storage_service
from src.services.parser import extract_text_from_bytes

logger = logging.getLogger(__name__)

async def save_jd(
    request: Request,
    job_description: Annotated[str, Form(...)],
    department: Annotated[str, Form(...)],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle job description save requests.
    Kicks off the processor agent. Job record is created only after processing is complete.
    """
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="User must belong to an organization to save a job description")
    
    logger.info(f"Received save JD request for department: {department}, org_id: {org_id}")
    
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
    background_tasks.add_task(run_jd_agent, raw_text=job_description, job_id=job_id, department=department, org_id=org_id)
    background_tasks.add_task(initial_broadcast)
    
    return {
        "success": True,
        "message": "Job description processing started",
        "job_id": str(job_id),
        "department": department
    }

async def get_jobs(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Retrieve all jobs.
    """
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return []
    
    logger.info(f"Fetching all jobs for org_id: {org_id}")
    repo = JobRepository(db)
    jobs = await repo.get_all_jobs(org_id=org_id)
    
    if jobs is None:
        logger.warning("JobRepository.get_all_jobs() returned None!")
        return []
    
    formatted_jobs = []
    for job in jobs:
        # ... (rest of the code)
        resumes = []
        if job.get("resumes"):
            for resume in job["resumes"]:
                resumes.append({
                    "id": resume.get("id"),
                    "original_filename": resume.get("name") or "Unknown",
                    "structured_data": {"rank": resume.get("rank")},
                    "analysis_id": resume.get("analysis_id")
                })
        
        formatted_jobs.append({
            "id": job["id"],
            "job_title": job.get("title") or "Untitled Job",
            "department": job.get("department") or "General",
            "markdown_text": job.get("markdown_content") or job.get("raw_text") or "",
            "resumes": resumes
        })
    
    return formatted_jobs

async def upload_resume(
    request: Request,
    job_id: Annotated[uuid.UUID, Form(...)],
    resume: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle resume upload for a specific job.
    """
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="User must belong to an organization to upload a resume")
        
    logger.info(f"Received resume upload for job_id: {job_id}, filename: {resume.filename}, org_id: {org_id}")
    
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
            org_id=org_id
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
        file_response = storage_service.get_file(resume["storage_key"])
        
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
                storage_service.delete_file(skeleton_resume.storage_key)
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

async def delete_job_endpoint(request: Request, job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a specific job and all its associated resumes/analyses.
    """
    org_id = getattr(request.state, "org_id", None)
    logger.info(f"Deleting job: {job_id} for org_id: {org_id}")
    
    # 1. Check if job belongs to org before deleting
    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if job and org_id and str(job.get("org_id")) != str(org_id):
         from fastapi import HTTPException
         raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    
    # 2. Cancel any active agents for this job
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
                storage_service.delete_file(resume.storage_key)
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

async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a specific job by ID.
    """
    logger.info(f"Fetching job: {job_id}")
    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
        return {"success": False, "message": "Job not found"}
    
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
    
    return {
        "id": str(job["id"]),
        "job_title": job.get("title") or "Untitled Job",
        "department": job.get("department") or "General",
        "markdown_text": job.get("markdown_content") or job.get("raw_text") or "",
        "raw_text": job.get("raw_text") or "",
        "resumes": resumes
    }
