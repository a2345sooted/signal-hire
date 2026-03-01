import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from src.models.db_models import OrgRole

class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    slug: str

class OrganizationCreate(BaseModel):
    name: str

class OrganizationMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    email: str
    role: OrgRole
    created_at: datetime
    status: str # "ACTIVE" or "PENDING"
    accepted_email: Optional[str] = None

class OrganizationInviteCreate(BaseModel):
    email: str
    role: OrgRole

class OrganizationInviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: OrgRole
    inviter_id: uuid.UUID
    expires_at: datetime
    created_at: datetime

class OrganizationInviteDetailResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    org_name: str
    email: str
    role: OrgRole
    inviter_email: Optional[str] = None
    expires_at: datetime
