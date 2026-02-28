import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Job, Resume, JobNote, Embedding


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add_job_note(self, job_id: uuid.UUID, user_id: uuid.UUID, content: str) -> uuid.UUID:
        """Add a note to a job"""
        note = JobNote(job_id=job_id, user_id=user_id, content=content)
        self.session.add(note)
        await self.session.flush()
        return note.id

    async def get_job_note_by_id(self, note_id: uuid.UUID) -> Optional[JobNote]:
        """Retrieve a specific job note by ID"""
        result = await self.session.execute(
            select(JobNote).where(JobNote.id == note_id)
        )
        return result.scalar_one_or_none()

    async def update_job_note(self, note_id: uuid.UUID, content: str) -> bool:
        """Update a specific job note's content"""
        note = await self.get_job_note_by_id(note_id)
        if not note:
            return False
        
        note.content = content
        await self.session.flush()
        return True

    async def delete_job_note(self, note_id: uuid.UUID) -> bool:
        """Delete a specific job note"""
        note = await self.get_job_note_by_id(note_id)
        if not note:
            return False
            
        await self.session.delete(note)
        await self.session.flush()
        return True

    async def attach_candidate(self, job_id: uuid.UUID, candidate_id: uuid.UUID) -> uuid.UUID:
        """Attach a candidate to a job"""
        from ..models.db_models import JobAttachment
        
        # Check if already attached
        stmt = select(JobAttachment).where(
            JobAttachment.job_id == job_id,
            JobAttachment.candidate_id == candidate_id
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing.id
            
        attachment = JobAttachment(job_id=job_id, candidate_id=candidate_id)
        self.session.add(attachment)
        await self.session.flush()
        return attachment.id

    async def detach_candidate(self, job_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
        """Detach a candidate from a job"""
        from ..models.db_models import JobAttachment
        
        stmt = select(JobAttachment).where(
            JobAttachment.job_id == job_id,
            JobAttachment.candidate_id == candidate_id
        )
        result = await self.session.execute(stmt)
        attachment = result.scalar_one_or_none()
        
        if not attachment:
            return False
            
        await self.session.delete(attachment)
        await self.session.flush()
        return True

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
    
    async def add_embeddings(
        self,
        job_id: Optional[uuid.UUID] = None,
        candidate_id: Optional[uuid.UUID] = None,
        resume_id: Optional[uuid.UUID] = None,
        embeddings: List[Dict[str, Any]] = None
    ):
        """Add multiple embeddings to an entity"""
        if not embeddings:
            return
            
        for emb_data in embeddings:
            emb = Embedding(
                job_id=job_id,
                candidate_id=candidate_id,
                resume_id=resume_id,
                embedding_type=emb_data["type"],
                vector=emb_data["vector"],
                metadata_json=emb_data.get("metadata")
            )
            self.session.add(emb)
        await self.session.flush()

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

        if embedding:
            emb = Embedding(
                job_id=job.id,
                embedding_type="legacy",
                vector=embedding
            )
            self.session.add(emb)
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
            org_id=org_id
        )
        self.session.add(job)
        await self.session.flush()

        if embedding:
            emb = Embedding(
                job_id=job.id,
                embedding_type="legacy",
                vector=embedding
            )
            self.session.add(emb)
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
            # Delete existing embeddings of type 'legacy' and add new one
            # Alternatively, we could just add a new one, but for 'update' it usually means replacement
            from sqlalchemy import delete
            await self.session.execute(
                delete(Embedding).where(Embedding.job_id == job_id, Embedding.embedding_type == "legacy")
            )
            emb = Embedding(
                job_id=job_id,
                embedding_type="legacy",
                vector=embedding
            )
            self.session.add(emb)
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

        # Get attached candidates
        from ..models.db_models import JobAttachment, JobRecommendation, Candidate
        attached_result = await self.session.execute(
            select(Candidate).join(JobAttachment).where(JobAttachment.job_id == job_id)
        )
        attached_candidates = attached_result.scalars().all()

        # Get recommended candidates
        recommended_result = await self.session.execute(
            select(Candidate).join(JobRecommendation).where(JobRecommendation.job_id == job_id)
        )
        recommended_candidates = recommended_result.scalars().all()

        # Get embeddings
        from ..models.db_models import Embedding
        emb_result = await self.session.execute(
            select(Embedding)
            .where(Embedding.job_id == job_id, Embedding.embedding_type == "legacy")
            .order_by(Embedding.created_at.desc())
        )
        legacy_embedding = emb_result.scalars().first()

        return {
            "id": str(job.id),
            "org_id": str(job.org_id) if job.org_id else None,
            "title": job.title,
            "client_name": job.client_name,
            "raw_text": job.raw_text,
            "markdown_content": job.markdown_content,
            "structured_data": job.structured_data,
            "embedding": legacy_embedding.vector if legacy_embedding else None,
            "location": job.location,
            "work_arrangement": job.work_arrangement,
            "hybrid_days_per_week": job.hybrid_days_per_week,
            "pay_range_min": job.pay_range_min,
            "pay_range_max": job.pay_range_max,
            "pay_type": job.pay_type,
            "employment_type": job.employment_type,
            "offers_relocation": job.offers_relocation,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "notes": notes,
            "attached_candidates": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "location": c.location
                }
                for c in attached_candidates
            ],
            "recommended_candidates": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "email": c.email
                }
                for c in recommended_candidates
            ]
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
                (1 - Embedding.vector.cosine_distance(query_embedding)).label("similarity")
            )
            .join(Embedding, Embedding.job_id == Job.id)
            .where(Embedding.embedding_type == "legacy")
            .order_by(Embedding.vector.cosine_distance(query_embedding))
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
