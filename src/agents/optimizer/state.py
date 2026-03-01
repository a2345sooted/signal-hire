import uuid
from typing import List, Dict, Any, Optional
from typing_extensions import TypedDict
from ...agents.utils import BaseAgentState
from ...models.resume import OptimizationPlanSchema, ResumeSchema

class OptimizerMetadata(TypedDict):
    task_type: str
    status: Optional[str]

class OptimizerState(BaseAgentState):
    # IDs
    thread_id: str
    candidate_id: str
    job_id: str
    resume_id: str # Original resume ID
    org_id: Optional[uuid.UUID]
    
    # Context
    job_data: Dict[str, Any]
    resume_data: Dict[str, Any]
    analysis_data: Dict[str, Any]
    
    # Processed Data
    optimization_plan: Optional[OptimizationPlanSchema]
    optimized_resume: Optional[ResumeSchema]
    
    # Results
    new_resume_id: Optional[uuid.UUID]
    
    # Metadata
    metadata: OptimizerMetadata
    messages: List[str]
