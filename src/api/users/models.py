import uuid
from datetime import datetime
from pydantic import BaseModel

class UserResponse(BaseModel):
    id: uuid.UUID
    sub: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True
