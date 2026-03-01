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

    async def attach_candidate(self, job_id: uuid.UUID, candidate_id: uuid.UUID, resume_id: Optional[uuid.UUID] = None) -> uuid.UUID:
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
            if resume_id is not None:
                existing.resume_id = resume_id
                await self.session.flush()
            return existing.id
            
        attachment = JobAttachment(job_id=job_id, candidate_id=candidate_id, resume_id=resume_id)
        self.session.add(attachment)
        await self.session.flush()
        return attachment.id

    async def detach_candidate(self, job_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
        """Detach a candidate from a job and clean up optimized resumes."""
        from ..models.db_models import JobAttachment, Resume, ProcessingTask
        from sqlalchemy import delete
        
        stmt = select(JobAttachment).where(
            JobAttachment.job_id == job_id,
            JobAttachment.candidate_id == candidate_id
        )
        result = await self.session.execute(stmt)
        attachment = result.scalar_one_or_none()
        
        if not attachment:
            return False
            
        # 1. Find all optimized resumes for this specific job-candidate pair
        # We also want to delete their storage and tasks, but repository is usually DB-only.
        # However, following the pattern in delete_resume.py, we should ideally handle it.
        # For now, let's at least delete from DB.
        
        resume_stmt = select(Resume).where(
            Resume.candidate_id == candidate_id,
            Resume.job_id == job_id,
            Resume.is_optimized == True
        )
        resume_result = await self.session.execute(resume_stmt)
        optimized_resumes = resume_result.scalars().all()
        
        for res in optimized_resumes:
            # Cancel tasks in DB for this resume
            await self.session.execute(
                delete(ProcessingTask).where(ProcessingTask.resume_id == res.id)
            )
            # Storage cleanup should probably happen in the API layer or a service,
            # but let's see if we can do it here or if we should move this logic to API.
            
            # For now, let's just delete the resume record. 
            # Cascades (if any) will handle related records like embeddings/analyses.
            # Analysis model has resume_id with ondelete="CASCADE".
            # Embedding model has resume_id with ondelete="CASCADE".
            await self.session.delete(res)

        await self.session.delete(attachment)
        await self.session.flush()
        return True

    async def get_attached_jobs(self, candidate_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Retrieve all jobs a candidate is attached to"""
        from ..models.db_models import JobAttachment, Job
        
        stmt = (
            select(Job)
            .join(JobAttachment, Job.id == JobAttachment.job_id)
            .where(JobAttachment.candidate_id == candidate_id)
        )
        result = await self.session.execute(stmt)
        jobs = result.scalars().all()
        
        return [
            {
                "id": str(job.id),
                "title": job.title,
                "org_id": job.org_id,
                "raw_text": job.raw_text,
                "structured_data": job.structured_data,
                "markdown_content": job.markdown_content
            }
            for job in jobs
        ]

    async def get_attached_candidates(self, job_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Retrieve all candidates attached to a job"""
        from ..models.db_models import JobAttachment, Candidate
        
        stmt = (
            select(Candidate)
            .join(JobAttachment, Candidate.id == JobAttachment.candidate_id)
            .where(JobAttachment.job_id == job_id)
        )
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()
        
        return [
            {
                "id": str(candidate.id),
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "location": candidate.location,
                "org_id": candidate.org_id
            }
            for candidate in candidates
        ]

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
        offers_relocation: bool = False,
        details: Optional[dict] = None
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
            offers_relocation=offers_relocation,
            details=details
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
        org_id: Optional[uuid.UUID] = None,
        location: Optional[str] = None,
        work_arrangement: Optional[str] = None,
        hybrid_days_per_week: Optional[int] = None,
        pay_range_min: Optional[int] = None,
        pay_range_max: Optional[int] = None,
        pay_type: Optional[str] = None,
        employment_type: Optional[str] = None,
        offers_relocation: bool = False,
        details: Optional[dict] = None
    ) -> uuid.UUID:
        """Insert a new job with a specific ID"""
        job = Job(
            id=job_id,
            title=title,
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
            offers_relocation=offers_relocation,
            details=details
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
        **kwargs
    ) -> bool:
        """Update an existing job's details using keyword arguments"""
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            return False
            
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
            elif key == "embedding" and value is not None:
                # Special handling for legacy embedding
                from sqlalchemy import delete
                await self.session.execute(
                    delete(Embedding).where(Embedding.job_id == job_id, Embedding.embedding_type == "legacy")
                )
                emb = Embedding(
                    job_id=job_id,
                    embedding_type="legacy",
                    vector=value
                )
                self.session.add(emb)
            
        await self.session.flush()
        return True

    async def _get_analysis_status_for_attachment(
        self, 
        candidate_id: uuid.UUID, 
        job_id: uuid.UUID, 
        attached_resume_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """Common logic to calculate analysis status for an attached job/candidate"""
        from ..models.db_models import Analysis, ProcessingTask
        from ..constants import TASK_ANALYSIS
        from datetime import datetime, timezone, timedelta
        
        # Check for analysis in DB
        analysis_stmt = (
            select(Analysis)
            .where(Analysis.candidate_id == candidate_id)
            .where(Analysis.job_id == job_id)
        )
        
        if attached_resume_id:
            analysis_stmt = analysis_stmt.where(Analysis.resume_id == attached_resume_id)
        
        analysis_stmt = analysis_stmt.order_by(Analysis.created_at.desc()).limit(1)
        
        analysis_result = await self.session.execute(analysis_stmt)
        analysis = analysis_result.scalar_one_or_none()

        # Check if a completed analysis exists
        is_ready = False
        score = None
        if analysis:
            content = analysis.content
            if content.get("status") == "completed":
                is_ready = True
                score = content.get("score")
            elif content.get("score") is not None:
                # Legacy check for score
                is_ready = True
                score = content.get("score")

        # Check for active task
        task_stmt = (
            select(ProcessingTask)
            .where(ProcessingTask.job_id == job_id)
            .where(ProcessingTask.candidate_id == candidate_id)
            .where(ProcessingTask.task_type == TASK_ANALYSIS)
        )
        
        # NOTE: We don't filter by attached_resume_id here to be more inclusive of any active analysis
        # for this candidate/job pair, which helps avoid 'pending' status when a task is running.
        
        task_stmt = task_stmt.order_by(ProcessingTask.created_at.desc()).limit(1)
        
        task_result = await self.session.execute(task_stmt)
        latest_task = task_result.scalar_one_or_none()
        
        is_processing = False
        if latest_task and latest_task.status in ["starting", "processing"]:
            task_time = latest_task.created_at
            if task_time.tzinfo is None:
                task_time = task_time.replace(tzinfo=timezone.utc)
            
            # It's only truly processing if the task is NOT stuck
            now = datetime.now(timezone.utc)
            last_activity = latest_task.updated_at or latest_task.created_at
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            
            is_stuck = (now - last_activity).total_seconds() / 60 >= 10 # 10 minute timeout
            
            if not is_stuck:
                if not is_ready:
                    is_processing = True
                else:
                    analysis_updated_at = analysis.updated_at or analysis.created_at
                    if analysis_updated_at.tzinfo is None:
                        analysis_updated_at = analysis_updated_at.replace(tzinfo=timezone.utc)
                    
                    if task_time > (analysis_updated_at + timedelta(seconds=5)):
                        is_processing = True

        analysis_status = "processing" if is_processing else ("ready" if is_ready else "pending")
        
        return {
            "analysis_status": analysis_status,
            "analysis_score": score,
            "is_analysis_processing": is_processing
        }

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
        from ..models.db_models import JobAttachment, JobRecommendation, Candidate, Analysis

        attached_result = await self.session.execute(
            select(Candidate).join(JobAttachment).where(JobAttachment.job_id == job_id)
        )
        attached_candidates = attached_result.scalars().all()

        # Build attached_candidates with analysis status and score
        from ..agents.analyzer.run import is_analysis_active
        formatted_attached_candidates = []
        
        # Get attached candidates with their specific resumes
        from ..models.db_models import JobAttachment, Candidate, Analysis
        stmt = (
            select(Candidate, JobAttachment.resume_id)
            .join(JobAttachment, Candidate.id == JobAttachment.candidate_id)
            .where(JobAttachment.job_id == job_id)
        )
        attached_result = await self.session.execute(stmt)
        attached_rows = attached_result.all()

        for row in attached_rows:
            c = row.Candidate
            attached_resume_id = row.resume_id

            # Use common status logic
            status_data = await self._get_analysis_status_for_attachment(
                candidate_id=c.id,
                job_id=job_id,
                attached_resume_id=attached_resume_id
            )

            formatted_attached_candidates.append({
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "location": c.location,
                "analysis_status": status_data["analysis_status"],
                "analysis_score": status_data["analysis_score"],
                "is_analysis_processing": status_data["is_analysis_processing"],
                "attached_resume_id": str(attached_resume_id) if attached_resume_id else None
            })

        # Get recommended candidates
        final_recommended_candidates = []
        
        # Get embeddings
        from ..models.db_models import Embedding
        emb_result = await self.session.execute(
            select(Embedding)
            .where(Embedding.job_id == job_id, Embedding.embedding_type == "legacy")
            .order_by(Embedding.created_at.desc())
            .limit(1)
        )
        legacy_embedding = emb_result.scalar_one_or_none()

        if legacy_embedding:
            # Find top 3 similar candidates using vector similarity
            # We exclude candidates that are already attached
            attached_candidate_ids = [uuid.UUID(c["id"]) for c in formatted_attached_candidates]
            
            similar_candidates_query = (
                select(
                    Candidate,
                    (1 - Embedding.vector.cosine_distance(legacy_embedding.vector)).label("similarity")
                )
                .join(Resume, Candidate.id == Resume.candidate_id)
                .join(Embedding, Resume.id == Embedding.resume_id)
                .where(Embedding.embedding_type == "legacy")
                .where(Candidate.id.notin_(attached_candidate_ids))
                .order_by(Embedding.vector.cosine_distance(legacy_embedding.vector))
                .limit(3)
            )
            similar_candidates_result = await self.session.execute(similar_candidates_query)
            for row in similar_candidates_result.all():
                c = row.Candidate
                final_recommended_candidates.append({
                    "id": str(c.id),
                    "name": c.name,
                    "email": c.email
                })

        # Fallback to JobRecommendation table if no vector recommendations found
        if not final_recommended_candidates:
            recommended_result = await self.session.execute(
                select(Candidate).join(JobRecommendation).where(JobRecommendation.job_id == job_id)
            )
            db_recommended_candidates = recommended_result.scalars().all()
            final_recommended_candidates = [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "email": c.email
                }
                for c in db_recommended_candidates
            ]

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
            "details": job.details,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "notes": notes,
            "attached_candidates": formatted_attached_candidates,
            "recommended_candidates": final_recommended_candidates
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
                        "is_optimized": resume.is_optimized,
                        "analysis_id": str([a.id for a in job.analyses if a.candidate_id == resume.candidate_id][0]) if any(a.candidate_id == resume.candidate_id for a in job.analyses) else None
                    }
                    for resume in job.resumes if not resume.is_optimized or str(resume.job_id) == str(job.id)
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
