import uuid
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Candidate, CandidateNote


class CandidateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_candidate(
        self, 
        name: str, 
        email: str, 
        org_id: Optional[uuid.UUID] = None,
        phone: Optional[str] = None,
        location: Optional[str] = None,
        citizenship: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        engagement_types: Optional[list[str]] = None,
        work_preference: Optional[list[str]] = None,
        open_to_relocation: Optional[bool] = False
    ) -> uuid.UUID:
        """Create a new candidate"""
        candidate = Candidate(
            name=name, 
            email=email, 
            org_id=org_id,
            phone=phone,
            location=location,
            citizenship=citizenship,
            linkedin_url=linkedin_url,
            engagement_types=engagement_types,
            work_preference=work_preference,
            open_to_relocation=open_to_relocation
        )
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
            "phone": candidate.phone,
            "location": candidate.location,
            "citizenship": candidate.citizenship,
            "linkedin_url": candidate.linkedin_url,
            "engagement_types": candidate.engagement_types or [],
            "work_preference": candidate.work_preference or [],
            "open_to_relocation": candidate.open_to_relocation or False,
            "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
            "attached_jobs": [
                {
                    "id": str(job.id),
                    "title": job.title,
                    "status": "attached"  # Stubbed status
                }
                for job in jobs
            ],
            "recommended_jobs": [],
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
                "phone": candidate.phone,
                "location": candidate.location,
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

    async def get_note_by_id(self, note_id: uuid.UUID) -> Optional[CandidateNote]:
        """Retrieve a specific note by ID"""
        result = await self.session.execute(
            select(CandidateNote).where(CandidateNote.id == note_id)
        )
        return result.scalar_one_or_none()

    async def update_note(self, note_id: uuid.UUID, content: str) -> bool:
        """Update a specific note's content"""
        note = await self.get_note_by_id(note_id)
        if not note:
            return False
        
        note.content = content
        await self.session.flush()
        return True

    async def delete_note(self, note_id: uuid.UUID) -> bool:
        """Delete a specific note"""
        note = await self.get_note_by_id(note_id)
        if not note:
            return False
            
        await self.session.delete(note)
        await self.session.flush()
        return True

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

    async def delete_candidate(self, candidate_id: uuid.UUID) -> bool:
        """Delete a candidate by ID"""
        result = await self.session.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if candidate:
            await self.session.delete(candidate)
            await self.session.flush()
            return True
        return False

    async def update_candidate(
        self, 
        candidate_id: uuid.UUID, 
        name: Optional[str] = None, 
        email: Optional[str] = None,
        phone: Optional[str] = None,
        location: Optional[str] = None,
        citizenship: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        engagement_types: Optional[list[str]] = None,
        work_preference: Optional[list[str]] = None,
        open_to_relocation: Optional[bool] = None
    ) -> bool:
        """Update a candidate's details"""
        result = await self.session.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            return False
        
        if name is not None:
            candidate.name = name
        if email is not None:
            candidate.email = email
        if phone is not None:
            candidate.phone = phone
        if location is not None:
            candidate.location = location
        if citizenship is not None:
            candidate.citizenship = citizenship
        if linkedin_url is not None:
            candidate.linkedin_url = linkedin_url
        if engagement_types is not None:
            candidate.engagement_types = engagement_types
        if work_preference is not None:
            candidate.work_preference = work_preference
        if open_to_relocation is not None:
            candidate.open_to_relocation = open_to_relocation
            
        await self.session.flush()
        return True
