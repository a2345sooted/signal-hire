import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.resume_repository import ResumeRepository

logger = logging.getLogger(__name__)

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
