import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

from ...agents.registry import get_resume_agent
from ...agents.utils import generate_thread_id
from ...constants import TASK_RESUME, CONFIG_THREAD_ID_KEY
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, cancel_agent_task

logger = logging.getLogger(__name__)

# Track active resume processing tasks
_active_resume_tasks: Dict[str, asyncio.Task] = {}

async def run_resume_agent(
    thread_id_id: Optional[str] = None,
    file_key: Optional[str] = None,
    original_filename: Optional[str] = None,
    job_id: Optional[uuid.UUID] = None,
    candidate_id: Optional[uuid.UUID] = None,
    resume_id: Optional[uuid.UUID] = None,
    raw_text: Optional[str] = None,
    org_id: Optional[uuid.UUID] = None
) -> Any:
    """
    Runs the full resume processing agent.
    Returns the final state dictionary.
    """
    # Prefer resume_id for consistency if thread_id_id is not provided
    if not thread_id_id and resume_id:
        thread_id_id = str(resume_id)
    elif not thread_id_id and candidate_id:
        # If no resume_id, try candidate_id (rare fallback)
        thread_id_id = str(candidate_id)

    thread_id = generate_thread_id("resume", job_id, thread_id_id)
    log_tag = "RESUME_PROCESSOR_RUN"
    logger.info(f"[{log_tag}] [{thread_id}] Starting resume agent...")
    
    # Check if this is already running
    existing_result = await handle_active_task(thread_id, _active_resume_tasks, log_tag)
    if existing_result is not None:
        return existing_result

    task = manage_active_task(thread_id, _active_resume_tasks)

    try:
        from ...agents.resume_processor.state import ResumeMetadata, ResumeState
        
        initial_metadata: ResumeMetadata = {
            "original_filename": original_filename or "resume.pdf",
            "existing_found": False,
            "iterations": 0,
            "task_type": TASK_RESUME
        }
        
        initial_state: ResumeState = {
            "raw_text": raw_text or "",
            "thread_id": thread_id,
            "file_key": file_key,
            "structured_data": None,
            "resume_id": resume_id,
            "candidate_id": candidate_id,
            "job_id": job_id,
            "org_id": org_id,
            "upload_response": None,
            "personal_info_mismatch_question": None,
            "metadata": initial_metadata
        }
        
        config = {"configurable": {CONFIG_THREAD_ID_KEY: thread_id}}

        def completion_check(state: ResumeState) -> bool:
            return bool(state.get("structured_data") and state.get("resume_id"))

        return await run_agent_with_retries(
            agent=get_resume_agent(),
            initial_state=initial_state,
            config=config,
            log_tag=log_tag,
            completion_check=completion_check,
            error_broadcaster=None
        )

    except asyncio.CancelledError:
        return {"status": "cancelled", "raw_text": raw_text, "thread_id": thread_id}
    finally:
        if _active_resume_tasks.get(thread_id) == task:
            del _active_resume_tasks[thread_id]

async def cancel_resume_agent(job_id: uuid.UUID):
    """Cancels a running resume agent task."""
    thread_id = generate_thread_id("resume", job_id)
    return await cancel_agent_task(thread_id, _active_resume_tasks, "RESUME_PROCESSOR_RUN")


def is_resume_processing_active(job_id: Optional[uuid.UUID] = None, resume_id: Optional[uuid.UUID] = None, candidate_id: Optional[uuid.UUID] = None) -> bool:
    """Check if a resume processing task is currently active."""
    # Try with resume_id if provided
    if resume_id:
        # We try both with and without job_id because it depends on how it was started
        thread_id_with_job = generate_thread_id("resume", job_id, str(resume_id))
        if thread_id_with_job in _active_resume_tasks:
            return True
        
        thread_id_no_job = generate_thread_id("resume", None, str(resume_id))
        if thread_id_no_job in _active_resume_tasks:
            return True
    
    # Try with candidate_id if provided (searching through all active tasks)
    if candidate_id:
        candidate_id_str = str(candidate_id)
        # Also try direct thread ID if it was started with candidate_id as thread_id_id
        thread_id_with_job = generate_thread_id("resume", job_id, candidate_id_str)
        if thread_id_with_job in _active_resume_tasks:
            return True
            
        thread_id_no_job = generate_thread_id("resume", None, candidate_id_str)
        if thread_id_no_job in _active_resume_tasks:
            return True

    # Fallback to just job_id if that's all we have
    if not resume_id and not candidate_id and job_id:
        thread_id = generate_thread_id("resume", job_id)
        return thread_id in _active_resume_tasks
        
    return False

