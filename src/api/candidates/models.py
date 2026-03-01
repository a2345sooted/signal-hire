import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr

class CandidateCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    location: Optional[str] = None
    citizenship: Optional[str] = None
    linkedin_url: Optional[str] = None
    engagement_types: Optional[list[str]] = None
    work_preference: Optional[list[str]] = None
    open_to_relocation: Optional[bool] = False

class NoteCreate(BaseModel):
    content: str

class NoteUpdate(BaseModel):
    content: str

class NoteResponse(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime
    user_id: uuid.UUID
    user_email: str

class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    citizenship: Optional[str] = None
    linkedin_url: Optional[str] = None
    engagement_types: Optional[list[str]] = None
    work_preference: Optional[list[str]] = None
    open_to_relocation: Optional[bool] = None

class JobBrief(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str | None = "attached"
    analysis_status: Optional[str] = "pending"
    analysis_score: Optional[int] = None
    is_analysis_processing: bool = False

class CandidateResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: Optional[str] = None
    location: Optional[str] = None
    citizenship: Optional[str] = None
    linkedin_url: Optional[str] = None
    engagement_types: list[str] = []
    work_preference: list[str] = []
    open_to_relocation: bool = False
    created_at: Optional[datetime] = None
    current_resume_structured_data: Optional[dict] = None
    attached_jobs: list[JobBrief] = []
    recommended_jobs: list[JobBrief] = []
    notes: list[NoteResponse] = []

    class Config:
        from_attributes = True
