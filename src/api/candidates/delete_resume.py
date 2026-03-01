import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.database import get_db
from src.repositories.resume_repository import ResumeRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.processing_task_repository import ProcessingTaskRepository
from src.models.db_models import Candidate
from src.services.storage import storage_service
from src.agents.resume_processor.run import cancel_resume_agent
from src.agents.analyzer.run import cancel_analyzer_agent
from src.agents.optimizer.run import cancel_optimizer_agent

logger = logging.getLogger(__name__)

async def delete_resume(
    request: Request,
    candidate_id: uuid.UUID,
    resume_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific resume for a candidate.
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
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    # Verify candidate exists and belongs to org
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Not authorized to access this candidate")

    resume_repo = ResumeRepository(db)
    resume = await resume_repo.get_resume_by_id(resume_id)
    
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    if str(resume.get("candidate_id")) != str(candidate_id):
         raise HTTPException(status_code=400, detail="Resume does not belong to this candidate")

    # Delete from storage if key exists
    storage_key = resume.get("storage_key")
    if storage_key:
        try:
            await storage_service.delete_file(storage_key)
            logger.info(f"Deleted file {storage_key} from S3 for resume {resume_id}")
        except Exception as e:
            logger.error(f"Failed to delete file {storage_key} from S3: {e}")
            # We continue with DB deletion even if S3 fails, or should we?
            # Usually better to keep DB and storage in sync, but if file is already gone it's fine.

    # Cancel any active tasks in memory
    job_id = resume.get("job_id")
    if job_id:
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        await cancel_resume_agent(job_id=job_id, resume_id=resume_id)
        await cancel_analyzer_agent(job_id=job_id, candidate_id=candidate_id, resume_id=resume_id)
        await cancel_optimizer_agent(job_id=job_id, candidate_id=candidate_id, resume_id=resume_id)
    else:
        # If no job_id, try to cancel with candidate_id or just resume_id
        await cancel_resume_agent(resume_id=resume_id)

    # Cancel tasks in DB
    task_repo = ProcessingTaskRepository(db)
    await task_repo.cancel_tasks_by_resume_id(resume_id)

    # Delete from DB
    success = await resume_repo.delete_resume(resume_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete resume from database")
    
    await db.commit()
    
    logger.info(f"Deleted resume {resume_id} for candidate {candidate_id}")
    
    return {
        "success": True,
        "message": "Resume deleted successfully"
    }
