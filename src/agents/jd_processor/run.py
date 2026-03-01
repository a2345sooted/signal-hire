import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Union

from ...agents.registry import get_jd_agent
from ...agents.utils import generate_thread_id
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, cancel_agent_task

from ...database import AsyncSessionLocal
from ...repositories.processing_task_repository import ProcessingTaskRepository

logger = logging.getLogger(__name__)

# Track active JD processing tasks
_active_jd_tasks: Dict[str, asyncio.Task] = {}

async def run_jd_agent(
    raw_text: str, 
    thread_id_id: Optional[str] = None,
    job_id: Optional[uuid.UUID] = None,
    org_id: Optional[uuid.UUID] = None
) -> Union[Dict[str, Any], Any]:
    """
    Runs the full job description agent (parsing, analysis, and markdown generation).
    Returns the final state dictionary.
    """
    thread_id = generate_thread_id("jd", job_id, thread_id_id)
    log_tag = "JD_PROCESSOR_RUN"
    logger.info(f"[{log_tag}] [{thread_id}] Starting JD agent...")
    
    # Check if this is already running
    existing_result = await handle_active_task(thread_id, _active_jd_tasks, log_tag)
    if existing_result is not None:
        return existing_result

    task = manage_active_task(thread_id, _active_jd_tasks)

    try:
        from ...agents.jd_processor.state import JDState

        initial_state: JDState = {
            "thread_id": thread_id,
            "raw_text": raw_text,
            "markdown": "",
            "structured_data": None,
            "job_id": job_id,
            "org_id": org_id
        }
        
        config = {"configurable": {"thread_id": thread_id}}
        
        def completion_check(state: JDState) -> bool:
            return bool(state.get("markdown") and state.get("structured_data"))

        return await run_agent_with_retries(
            agent=get_jd_agent(),
            initial_state=initial_state,
            config=config,
            log_tag=log_tag,
            completion_check=completion_check,
            error_broadcaster=None
        )

    except asyncio.CancelledError:
        return {"status": "cancelled", "raw_text": raw_text, "thread_id": thread_id}
    finally:
        if _active_jd_tasks.get(thread_id) == task:
            del _active_jd_tasks[thread_id]

async def cancel_jd_agent(job_id: uuid.UUID):
    """Cancels a running JD agent task."""
    thread_id = generate_thread_id("jd", job_id)
    return await cancel_agent_task(thread_id, _active_jd_tasks, "JD_PROCESSOR_RUN")


async def is_jd_processing_active(job_id: uuid.UUID) -> bool:
    """Check if a JD processing task is currently active for a given job_id."""
    async with AsyncSessionLocal() as db:
        repo = ProcessingTaskRepository(db)
        return await repo.is_task_active(task_type="jd", job_id=job_id)

