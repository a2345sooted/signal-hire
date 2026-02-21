import logging
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

class CandidateCreate(BaseModel):
    name: str
    email: EmailStr

class NoteCreate(BaseModel):
    content: str

class NoteResponse(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime
    user_id: uuid.UUID
    user_email: str

class JobBrief(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str | None = "attached"

class CandidateResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    created_at: datetime
    jobs: list[JobBrief] = []
    notes: list[NoteResponse] = []

    class Config:
        from_attributes = True

async def create_candidate(
    request: Request,
    body: CandidateCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Handle candidate creation requests.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check if user has access to this organization
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    logger.info(f"Creating candidate '{body.name}' for organization '{x_org_slug}'")
    
    candidate_repo = CandidateRepository(db)
    # Use get_or_create logic if preferred, but here we'll just create or fail if unique constraints existed
    # For now, let's just create.
    candidate_id = await candidate_repo.create_candidate(
        name=body.name,
        email=body.email,
        org_id=org.id
    )
    
    await db.commit()
    
    # Fetch the created candidate to return it
    candidate_data = await candidate_repo.get_candidate_by_id(candidate_id)
    
    return {
        "success": True,
        "candidate": candidate_data
    }

async def get_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific candidate by ID.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    candidate_repo = CandidateRepository(db)
    candidate = await candidate_repo.get_candidate_by_id(candidate_id)
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    return {
        "success": True,
        "candidate": candidate
    }

async def get_candidates(
    request: Request,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all candidates for an organization.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    candidate_repo = CandidateRepository(db)
    candidates = await candidate_repo.get_candidates(org.id)
    
    return {
        "success": True,
        "candidates": candidates
    }

async def add_candidate_note(
    request: Request,
    candidate_id: uuid.UUID,
    body: NoteCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to a candidate.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    candidate_repo = CandidateRepository(db)
    # Ideally check if candidate exists and belongs to the org
    candidate = await candidate_repo.get_candidate_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    note_id = await candidate_repo.add_note(
        candidate_id=candidate_id,
        user_id=user_id,
        content=body.content
    )
    
    await db.commit()
    
    return {
        "success": True,
        "note_id": note_id
    }

async def get_candidate_notes(
    request: Request,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all notes for a candidate.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    candidate_repo = CandidateRepository(db)
    notes = await candidate_repo.get_notes(candidate_id)
    
    return {
        "success": True,
        "notes": notes
    }
