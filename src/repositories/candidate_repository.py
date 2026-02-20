import uuid
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Candidate


class CandidateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_candidate(self, name: str, org_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        """Create a new candidate"""
        candidate = Candidate(name=name, org_id=org_id)
        self.session.add(candidate)
        await self.session.flush()
        return candidate.id

    async def get_candidate_by_id(self, candidate_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve a candidate by ID"""
        result = await self.session.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        
        if not candidate:
            return None
            
        return {
            "id": str(candidate.id),
            "name": candidate.name,
            "created_at": candidate.created_at.isoformat() if candidate.created_at else None
        }

    async def get_or_create_candidate_by_name(self, name: str, org_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        """Simple get or create by name for now"""
        query = select(Candidate).where(Candidate.name == name)
        if org_id:
            query = query.where(Candidate.org_id == org_id)
        
        result = await self.session.execute(query.limit(1))
        candidate = result.scalar_one_or_none()
        if candidate:
            return candidate.id
        
        return await self.create_candidate(name, org_id=org_id)
