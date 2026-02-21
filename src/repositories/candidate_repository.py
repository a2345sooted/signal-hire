import uuid
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Candidate, CandidateNote


class CandidateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_candidate(self, name: str, email: str, org_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        """Create a new candidate"""
        candidate = Candidate(name=name, email=email, org_id=org_id)
        self.session.add(candidate)
        await self.session.flush()
        return candidate.id

    async def get_candidate_by_id(self, candidate_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve a candidate by ID along with their attached jobs and notes"""
        from ..models.db_models import Job, Analysis

        result = await self.session.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        
        if not candidate:
            return None
        
        # Get jobs via analyses
        jobs_query = select(Job).join(Analysis).where(Analysis.candidate_id == candidate_id)
        jobs_result = await self.session.execute(jobs_query)
        jobs = jobs_result.scalars().all()

        # Get notes
        notes = await self.get_notes(candidate_id)

        return {
            "id": str(candidate.id),
            "name": candidate.name,
            "email": candidate.email,
            "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
            "jobs": [
                {
                    "id": str(job.id),
                    "title": job.title,
                    "status": "attached"  # Stubbed status
                }
                for job in jobs
            ],
            "notes": notes
        }

    async def get_candidates(self, org_id: uuid.UUID) -> list[Dict[str, Any]]:
        """Retrieve all candidates for an organization"""
        result = await self.session.execute(
            select(Candidate).where(Candidate.org_id == org_id)
        )
        candidates = result.scalars().all()
        
        return [
            {
                "id": str(candidate.id),
                "name": candidate.name,
                "email": candidate.email,
                "created_at": candidate.created_at.isoformat() if candidate.created_at else None
            }
            for candidate in candidates
        ]
    async def get_or_create_candidate_by_name(self, name: str, email: str, org_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        """Simple get or create by name/email for now"""
        query = select(Candidate).where(Candidate.email == email)
        if org_id:
            query = query.where(Candidate.org_id == org_id)
        
        result = await self.session.execute(query.limit(1))
        candidate = result.scalar_one_or_none()
        if candidate:
            return candidate.id
        
        return await self.create_candidate(name, email=email, org_id=org_id)

    async def add_note(self, candidate_id: uuid.UUID, user_id: uuid.UUID, content: str) -> uuid.UUID:
        """Add a note to a candidate"""
        note = CandidateNote(candidate_id=candidate_id, user_id=user_id, content=content)
        self.session.add(note)
        await self.session.flush()
        return note.id

    async def get_notes(self, candidate_id: uuid.UUID) -> list[Dict[str, Any]]:
        """Retrieve all notes for a candidate"""
        from ..models.db_models import User
        
        result = await self.session.execute(
            select(CandidateNote, User.email)
            .join(User, CandidateNote.user_id == User.id)
            .where(CandidateNote.candidate_id == candidate_id)
            .order_by(CandidateNote.created_at.desc())
        )
        notes = result.all()
        
        return [
            {
                "id": str(note.CandidateNote.id),
                "content": note.CandidateNote.content,
                "created_at": note.CandidateNote.created_at.isoformat() if note.CandidateNote.created_at else None,
                "user_id": str(note.CandidateNote.user_id),
                "user_email": note.email
            }
            for note in notes
        ]
