import logging
import json
from langchain_core.runnables import RunnableConfig

from ....agents.resume_processor.state import ResumeState
from ....api.ws.manager import manager

logger = logging.getLogger(__name__)

async def broadcast_started_node(state: ResumeState, config: RunnableConfig = None):
    """
    Broadcasts that the resume processing has started.
    This is the first node in the resume processing graph.
    """
    job_id = state.get("job_id")
    resume_id = state.get("resume_id")
    original_filename = state.get("metadata", {}).get("original_filename", "resume.pdf")

    if job_id and resume_id:
        logger.info(f"Sending initial broadcast for resume upload to job_id: {job_id}")
        await manager.broadcast_to_job(
            json.dumps({
                "status": "Initializing", 
                "message": f"Uploading and preparing resume: {original_filename}",
                "resume_id": str(resume_id),
                "completed": False
            }),
            str(job_id)
        )
    
    return {}
