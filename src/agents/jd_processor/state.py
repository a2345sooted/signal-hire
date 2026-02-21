import uuid
from typing import Optional, Dict, Any
from ...agents.utils import BaseAgentState


class JDState(BaseAgentState):
    # Input
    raw_text: str
    
    # Processed Data
    markdown: str
    structured_data: Optional[Dict[str, Any]]
    
    # DB Results
    job_id: Optional[uuid.UUID]
    org_id: Optional[uuid.UUID]
