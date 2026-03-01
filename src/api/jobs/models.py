import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class JobNoteCreate(BaseModel):
    content: str

class JobNoteUpdate(BaseModel):
    content: str

class JobNoteResponse(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime
    user_id: uuid.UUID
    user_email: str

class JobCreate(BaseModel):
    title: str
    client_name: str
    raw_text: Optional[str] = None
    location: Optional[str] = None
    work_arrangement: Optional[str] = None  # in-office, hybrid, remote
    hybrid_days_per_week: Optional[int] = None
    pay_range_min: Optional[int] = None
    pay_range_max: Optional[int] = None
    pay_type: Optional[str] = None  # salary, hourly
    employment_type: Optional[str] = None  # fte, w2, contract
    offers_relocation: bool = False

class JobUpdate(BaseModel):
    title: Optional[str] = None
    client_name: Optional[str] = None
    raw_text: Optional[str] = None
    location: Optional[str] = None
    work_arrangement: Optional[str] = None
    hybrid_days_per_week: Optional[int] = None
    pay_range_min: Optional[int] = None
    pay_range_max: Optional[int] = None
    pay_type: Optional[str] = None
    employment_type: Optional[str] = None
    offers_relocation: Optional[bool] = None

class AttachedCandidate(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    analysis_status: Optional[str] = "pending"
    analysis_score: Optional[int] = None
    is_analysis_processing: bool = False
    attached_resume_id: Optional[uuid.UUID] = None

class RecommendedCandidate(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str] = None

class JobResponse(BaseModel):
    id: str
    title: str
    client_name: Optional[str] = None
    raw_text: Optional[str] = None
    markdown_text: Optional[str] = None
    location: Optional[str] = None
    work_arrangement: Optional[str] = None
    hybrid_days_per_week: Optional[int] = None
    pay_range_min: Optional[int] = None
    pay_range_max: Optional[int] = None
    pay: Optional[str] = None
    pay_type: Optional[str] = None
    employment_type: Optional[str] = None
    offers_relocation: bool = False
    details: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    
    # New fields for list card
    owner_email: str = "user@example.com"  # Stubbed
    num_candidates: int = 0 # Stubbed
    attached_candidates: List[AttachedCandidate] = []
    recommended_candidates: List[RecommendedCandidate] = []
    notes: List[JobNoteResponse] = []

    class Config:
        from_attributes = True
        # Keep job_title for backward compatibility if any
        populate_by_name = True
