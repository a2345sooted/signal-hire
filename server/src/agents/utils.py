import uuid
from typing import TypedDict, Optional, Dict, Any

from ..constants import CONFIG_THREAD_ID_KEY, NO_THREAD_ID


class BaseAgentState(TypedDict):
    thread_id: Optional[str]

def generate_thread_id(prefix: str, job_id: Optional[uuid.UUID] = None, thread_id_id: Optional[str] = None) -> str:
    """
    Generates a consistent thread ID for an agent.
    
    Priority:
    1. job_id (prefixed)
    2. thread_id_id (prefixed)
    3. random UUID (prefixed if specified)
    """
    if job_id:
        return f"{prefix}_{job_id}"
    if thread_id_id:
        return f"{prefix}_{thread_id_id}"
    
    random_id = str(uuid.uuid4())
    return f"{prefix}_{random_id}" if prefix else random_id

def get_thread_id(state: Dict[str, Any], config: Any = None) -> str:
    """Extract thread_id from state or config."""
    return state.get("thread_id") or (config.get("configurable", {}).get(CONFIG_THREAD_ID_KEY, NO_THREAD_ID) if config else NO_THREAD_ID)

def strip_id_prefix(thread_id: str) -> str:
    """Remove prefix from thread ID (e.g., jd_, resume_)."""
    if thread_id.startswith("jd_"):
        return thread_id[3:]
    elif thread_id.startswith("resume_"):
        return thread_id[7:]
    elif thread_id.startswith("analysis_"):
        return thread_id[9:]
    return thread_id

def get_checkpoint_config(thread_id: str):
    return {
        "configurable": {
            CONFIG_THREAD_ID_KEY: thread_id,
            "checkpoint_ns": ""
        }
    }
