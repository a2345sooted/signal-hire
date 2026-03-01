import uuid
from typing import TypedDict, Optional, Dict, Any

from ..constants import CONFIG_THREAD_ID_KEY, NO_THREAD_ID


class BaseAgentState(TypedDict):
    thread_id: Optional[str]

def generate_thread_id(prefix: str, job_id: Optional[uuid.UUID] = None, thread_id_id: Optional[str] = None) -> str:
    """
    Generates a consistent thread ID for an agent.
    
    Priority:
    1. job_id AND thread_id_id (if both provided, joined with _)
    2. job_id (prefixed)
    3. thread_id_id (prefixed)
    4. random UUID (prefixed if specified)
    """
    if job_id and thread_id_id:
        return f"{prefix}_{job_id}_{thread_id_id}"
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
    elif thread_id.startswith("optimizer_"):
        return thread_id[10:]
    return thread_id

def extract_uuid_from_thread_id(thread_id: str) -> Optional[uuid.UUID]:
    """Attempts to extract the last UUID-like part of a thread ID."""
    clean_id = strip_id_prefix(thread_id)
    parts = clean_id.split("_")
    for part in reversed(parts):
        try:
            return uuid.UUID(part)
        except ValueError:
            continue
    return None

def get_checkpoint_config(thread_id: str):
    return {
        "configurable": {
            CONFIG_THREAD_ID_KEY: thread_id,
            "checkpoint_ns": ""
        }
    }

def get_task_id(thread_id: str) -> uuid.UUID:
    """Generates a deterministic UUID from a thread ID for use as a ProcessingTask primary key."""
    import hashlib
    # We use MD5 because it's 128 bits, which fits perfectly into a UUID
    hash_obj = hashlib.md5(thread_id.encode())
    return uuid.UUID(hash_obj.hexdigest())
