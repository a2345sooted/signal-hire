import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.resume_processor.run import cancel_resume_agent
from src.database import get_db
from src.repositories.resume_repository import ResumeRepository
from src.services.storage import storage_service

logger = logging.getLogger(__name__)

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
        
    return {
        "success": True,
        "cancelled": cancelled,
        "message": "Resume processing stopped and skeleton removed" if skeleton_resume else "Resume processing stopped"
    }
