import uuid
from typing import TypedDict, Optional, Dict, Any

from ...agents.utils import BaseAgentState


class ResumeMetadata(TypedDict):
    original_filename: str
    existing_found: bool
    iterations: int
    task_type: str

class ResumeState(BaseAgentState):
    # Input
    raw_text: str
    file_key: Optional[str]  # Minio key if applicable
    
    # Processed Data
    structured_data: Optional[Dict[str, Any]]
    
    # DB Results
    resume_id: Optional[uuid.UUID]
    candidate_id: Optional[uuid.UUID]
    job_id: Optional[uuid.UUID]
    org_id: Optional[uuid.UUID]
    
    # Messaging
    upload_response: Optional[str]
    personal_info_mismatch_question: Optional[str]
    
    # Metadata
    metadata: ResumeMetadata
