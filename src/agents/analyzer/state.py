import uuid
from typing import List, Dict, Any, Optional

from typing_extensions import TypedDict

from ...agents.utils import BaseAgentState
from ...models.analysis import ScoreBreakdown


class AnalyzerMetadata(TypedDict):
    task_type: str
    status: Optional[str]

class AnalyzerState(BaseAgentState):
    # IDs
    thread_id: str
    candidate_id: str
    job_id: str
    org_id: Optional[uuid.UUID]
    analysis_id: Optional[uuid.UUID]
    
    # Input
    resume_data: Dict[str, Any]
    job_data: Dict[str, Any]
    
    # Analysis results
    score: Optional[int]
    score_breakdown: Optional[ScoreBreakdown]
    scoring_reasoning: Optional[str]
    major_hits: List[str]
    minor_hits: List[str]
    major_gaps: List[str]
    minor_gaps: List[str]
    
    # Process management
    messages: List[str]
    personal_info_mismatch_question: Optional[str]
    
    # Metadata
    metadata: AnalyzerMetadata
