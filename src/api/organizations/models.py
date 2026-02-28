import uuid
from pydantic import BaseModel, ConfigDict

class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    name: str
    slug: str

class OrganizationCreate(BaseModel):
    name: str
