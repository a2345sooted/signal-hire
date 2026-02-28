import logging
import uuid
from fastapi import Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.resume_repository import ResumeRepository
from src.services.storage import storage_service

logger = logging.getLogger(__name__)

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
