import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Union

from ...agents.registry import get_jd_agent
from ...agents.utils import generate_thread_id
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, broadcast_agent_error, cancel_agent_task

logger = logging.getLogger(__name__)

# Track active JD processing tasks
_active_jd_tasks: Dict[str, asyncio.Task] = {}

async def run_jd_agent(
    raw_text: str, 
    thread_id_id: Optional[str] = None,
    job_id: Optional[uuid.UUID] = None,
    department: Optional[str] = None,
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
            "org_id": org_id,
            "department": department
        }
        
        config = {"configurable": {"thread_id": thread_id}}
        
        def completion_check(state: JDState) -> bool:
            return bool(state.get("markdown") and state.get("structured_data"))

        async def error_broadcaster(e: Exception):
            await broadcast_agent_error(
                job_id=job_id,
                thread_id=thread_id,
                error=e,
                log_tag=log_tag
            )

        return await run_agent_with_retries(
            agent=get_jd_agent(),
            initial_state=initial_state,
            config=config,
            log_tag=log_tag,
            completion_check=completion_check,
            error_broadcaster=error_broadcaster
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

    # Fallback (should not be reached due to raise above)
    raise RuntimeError("JD conversion failed unexpectedly")

