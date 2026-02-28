import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Job, Resume, JobNote


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add_job_note(self, job_id: uuid.UUID, user_id: uuid.UUID, content: str) -> uuid.UUID:
        """Add a note to a job"""
        note = JobNote(job_id=job_id, user_id=user_id, content=content)
        self.session.add(note)
        await self.session.flush()
        return note.id

    async def get_job_notes(self, job_id: uuid.UUID) -> list[Dict[str, Any]]:
        """Retrieve all notes for a job"""
        from ..models.db_models import User
        
        result = await self.session.execute(
            select(JobNote, User.email)
            .join(User, JobNote.user_id == User.id)
            .where(JobNote.job_id == job_id)
            .order_by(JobNote.created_at.desc())
        )
        notes = result.all()
        
        return [
            {
                "id": str(note.JobNote.id),
                "content": note.JobNote.content,
                "created_at": note.JobNote.created_at.isoformat() if note.JobNote.created_at else None,
                "user_id": str(note.JobNote.user_id),
                "user_email": note.email
            }
            for note in notes
        ]
    
    async def create_job(
        self,
        raw_text: Optional[str] = None,
        structured_data: Optional[dict] = None,
        embedding: Optional[List[float]] = None,
        title: Optional[str] = None,
        client_name: Optional[str] = None,
        markdown_content: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None,
        location: Optional[str] = None,
        work_arrangement: Optional[str] = None,
        hybrid_days_per_week: Optional[int] = None,
        pay_range_min: Optional[int] = None,
        pay_range_max: Optional[int] = None,
        pay_type: Optional[str] = None,
        employment_type: Optional[str] = None,
        offers_relocation: bool = False
    ) -> uuid.UUID:
        """Insert a new job with its embedding"""
        job = Job(
            title=title,
            client_name=client_name,
            raw_text=raw_text,
            markdown_content=markdown_content,
            structured_data=structured_data,
            embedding=embedding,
            org_id=org_id,
            location=location,
            work_arrangement=work_arrangement,
            hybrid_days_per_week=hybrid_days_per_week,
            pay_range_min=pay_range_min,
            pay_range_max=pay_range_max,
            pay_type=pay_type,
            employment_type=employment_type,
            offers_relocation=offers_relocation
        )
        self.session.add(job)
        await self.session.flush()
        return job.id

    async def create_job_with_id(
        self,
        job_id: uuid.UUID,
        raw_text: str,
        structured_data: dict,
        embedding: Optional[List[float]] = None,
        title: Optional[str] = None,
        markdown_content: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Insert a new job with a specific ID"""
        job = Job(
            id=job_id,
            title=title,
            raw_text=raw_text,
            markdown_content=markdown_content,
            structured_data=structured_data,
            embedding=embedding,
            org_id=org_id
        )
        self.session.add(job)
        await self.session.flush()
        return job.id
    
    async def update_job(
        self,
        job_id: uuid.UUID,
        title: Optional[str] = None,
        client_name: Optional[str] = None,
        structured_data: Optional[dict] = None,
        embedding: Optional[List[float]] = None,
        markdown_content: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None,
        location: Optional[str] = None,
        work_arrangement: Optional[str] = None,
        hybrid_days_per_week: Optional[int] = None,
        pay_range_min: Optional[int] = None,
        pay_range_max: Optional[int] = None,
        pay_type: Optional[str] = None,
        employment_type: Optional[str] = None,
        offers_relocation: Optional[bool] = None,
        raw_text: Optional[str] = None
    ) -> bool:
        """Update an existing job's details"""
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return False
            
        if title is not None:
            job.title = title
        if client_name is not None:
            job.client_name = client_name
        if structured_data is not None:
            job.structured_data = structured_data
        if embedding is not None:
            job.embedding = embedding
        if markdown_content is not None:
            job.markdown_content = markdown_content
        if org_id is not None:
            job.org_id = org_id
        if location is not None:
            job.location = location
        if work_arrangement is not None:
            job.work_arrangement = work_arrangement
        if hybrid_days_per_week is not None:
            job.hybrid_days_per_week = hybrid_days_per_week
        if pay_range_min is not None:
            job.pay_range_min = pay_range_min
        if pay_range_max is not None:
            job.pay_range_max = pay_range_max
        if pay_type is not None:
            job.pay_type = pay_type
        if employment_type is not None:
            job.employment_type = employment_type
        if offers_relocation is not None:
            job.offers_relocation = offers_relocation
        if raw_text is not None:
            job.raw_text = raw_text
            
        await self.session.flush()
        return True

    async def get_job_by_id(self, job_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve a job by ID"""
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return None
            
        # Get notes
        notes = await self.get_job_notes(job_id)

        return {
            "id": str(job.id),
            "org_id": str(job.org_id) if job.org_id else None,
            "title": job.title,
            "client_name": job.client_name,
            "raw_text": job.raw_text,
            "markdown_content": job.markdown_content,
            "structured_data": job.structured_data,
            "embedding": job.embedding,
            "location": job.location,
            "work_arrangement": job.work_arrangement,
            "hybrid_days_per_week": job.hybrid_days_per_week,
            "pay_range_min": job.pay_range_min,
            "pay_range_max": job.pay_range_max,
            "pay_type": job.pay_type,
            "employment_type": job.employment_type,
            "offers_relocation": job.offers_relocation,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "notes": notes
        }


    async def find_similar_jobs(
        self,
        query_embedding: List[float],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Find jobs similar to the query embedding using cosine similarity"""
        result = await self.session.execute(
            select(
                Job,
                (1 - Job.embedding.cosine_distance(query_embedding)).label("similarity")
            )
            .order_by(Job.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        
        rows = result.all()
        return [
            {
                "id": str(row.Job.id),
                "structured_data": row.Job.structured_data,
                "similarity": float(row.similarity)
            }
            for row in rows
        ]

    async def get_all_jobs(self, org_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        """Retrieve all jobs from the database including their resumes and analyses"""
        from sqlalchemy.orm import selectinload
        query = select(Job).options(
                selectinload(Job.resumes),
                selectinload(Job.analyses)
            )
        
        if org_id:
            query = query.where(Job.org_id == org_id)
            
        result = await self.session.execute(
            query.order_by(Job.created_at.desc())
        )
        jobs = result.scalars().all()
        return [
            {
                "id": str(job.id),
                "title": job.title,
                "client_name": job.client_name,
                "raw_text": job.raw_text,
                "markdown_content": job.markdown_content,
                "structured_data": job.structured_data,
                "location": job.location,
                "work_arrangement": job.work_arrangement,
                "hybrid_days_per_week": job.hybrid_days_per_week,
                "pay_range_min": job.pay_range_min,
                "pay_range_max": job.pay_range_max,
                "pay_type": job.pay_type,
                "employment_type": job.employment_type,
                "offers_relocation": job.offers_relocation,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "resumes": [
                    {
                        "id": str(resume.id),
                        "candidate_id": str(resume.candidate_id),
                        "name": resume.structured_data.get("contact", {}).get("name") or "Unknown",
                        "rank": resume.structured_data.get("rank") or 0, # Defaulting to 0 if not found
                        "analysis_id": str([a.id for a in job.analyses if a.candidate_id == resume.candidate_id][0]) if any(a.candidate_id == resume.candidate_id for a in job.analyses) else None
                    }
                    for resume in job.resumes
                ]
            }
            for job in jobs
        ]

    async def delete_job(self, job_id: uuid.UUID) -> bool:
        """Delete a job by ID"""
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job:
            await self.session.delete(job)
            await self.session.flush()
            return True
        return False
