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
        email: Optional[str] = None, 
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
        
        if attached_resume_id:
            task_stmt = task_stmt.where(ProcessingTask.resume_id == attached_resume_id)
            
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

    async def get_candidate_by_id(self, candidate_id: uuid.UUID, org_id: Optional[uuid.UUID] = None) -> Optional[Dict[str, Any]]:
        """Retrieve a candidate by ID along with their attached jobs and notes"""
        from ..models.db_models import Job, JobAttachment, CandidateRecommendation, Analysis
        from ..agents.resume_processor.run import is_resume_processing_active

        query = select(Candidate).where(Candidate.id == candidate_id)
        if org_id:
            query = query.where(Candidate.org_id == org_id)
            
        result = await self.session.execute(query)
        candidate = result.scalar_one_or_none()
        
        if not candidate:
            return None
        
        # Ensure we use the candidate's actual org_id for subsequent queries if not provided
        effective_org_id = org_id or candidate.org_id

        # Get attached jobs
        from ..models.db_models import Job, JobAttachment
        attached_query = (
            select(Job, JobAttachment.resume_id)
            .join(JobAttachment, Job.id == JobAttachment.job_id)
            .where(JobAttachment.candidate_id == candidate_id)
        )
        # Note: Attached jobs should naturally belong to the same org, 
        # but we can add a filter for safety if org_id is provided
        if effective_org_id:
            attached_query = attached_query.where(Job.org_id == effective_org_id)

        attached_result = await self.session.execute(attached_query)
        attached_rows = attached_result.all()


        # Get latest resume structured data
        from ..models.db_models import Resume
        resume_stmt = (
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .where(Resume.is_optimized == False) # GET ORIGINAL RESUME
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        resume_result = await self.session.execute(resume_stmt)
        latest_resume = resume_result.scalar_one_or_none()
        latest_resume_structured_data = latest_resume.structured_data if latest_resume else None

        # Check if resume is processing
        is_resume_processing = await is_resume_processing_active(candidate_id=candidate_id)

        # Get notes
        notes = await self.get_notes(candidate_id, org_id=effective_org_id)

        # Build attached_jobs with analysis status
        formatted_attached_jobs = []
        for row in attached_rows:
            job = row.Job
            attached_resume_id = row.resume_id

            # Use common status logic
            status_data = await self._get_analysis_status_for_attachment(
                candidate_id=candidate_id,
                job_id=job.id,
                attached_resume_id=attached_resume_id
            )

            formatted_attached_jobs.append({
                "id": str(job.id),
                "title": job.title,
                "client_name": job.client_name,
                "status": "attached",
                "analysis_status": status_data["analysis_status"],
                "analysis_score": status_data["analysis_score"],
                "is_analysis_processing": status_data["is_analysis_processing"],
                "attached_resume_id": str(attached_resume_id) if attached_resume_id else None
            })

        # Get recommended jobs
        final_recommended_jobs = []
        if latest_resume:
            from ..models.db_models import Embedding
            # Find the latest embedding for this resume
            emb_stmt = (
                select(Embedding)
                .where(Embedding.resume_id == latest_resume.id)
                .order_by(Embedding.created_at.desc())
                .limit(1)
            )
            emb_result = await self.session.execute(emb_stmt)
            resume_embedding = emb_result.scalar_one_or_none()

            if resume_embedding:
                # Find top 3 similar jobs using vector similarity
                # We exclude jobs that are already attached
                attached_job_ids = [uuid.UUID(j["id"]) for j in formatted_attached_jobs]
                
                similar_jobs_query = (
                    select(
                        Job,
                        (1 - Embedding.vector.cosine_distance(resume_embedding.vector)).label("similarity")
                    )
                    .join(Embedding, Embedding.job_id == Job.id)
                    .where(Embedding.embedding_type == "full")
                    .where(Job.id.notin_(attached_job_ids))
                )
                if effective_org_id:
                    similar_jobs_query = similar_jobs_query.where(Job.org_id == effective_org_id)
                
                similar_jobs_query = (
                    similar_jobs_query
                    .order_by(Embedding.vector.cosine_distance(resume_embedding.vector))
                    .limit(3)
                )
                similar_jobs_result = await self.session.execute(similar_jobs_query)
                for row in similar_jobs_result.all():
                    job = row.Job
                    final_recommended_jobs.append({
                        "id": str(job.id),
                        "title": job.title,
                        "client_name": job.client_name
                    })

        # Fallback to CandidateRecommendation table if no vector recommendations found
        if not final_recommended_jobs:
            recommended_query = select(Job).join(CandidateRecommendation).where(CandidateRecommendation.candidate_id == candidate_id)
            if effective_org_id:
                recommended_query = recommended_query.where(Job.org_id == effective_org_id)
            recommended_result = await self.session.execute(recommended_query)
            db_recommended_jobs = recommended_result.scalars().all()
            final_recommended_jobs = [
                {
                    "id": str(job.id),
                    "title": job.title,
                    "client_name": job.client_name
                }
                for job in db_recommended_jobs
            ]

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
            "latest_resume_structured_data": latest_resume_structured_data,
            "is_resume_processing": is_resume_processing,
            "attached_jobs": formatted_attached_jobs,
            "recommended_jobs": final_recommended_jobs,
            "notes": notes
        }

    async def get_latest_resume(self, candidate_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve the latest resume for a candidate"""
        from ..models.db_models import Resume
        
        stmt = (
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        resume = result.scalar_one_or_none()
        
        if not resume:
            return None
            
        return {
            "id": str(resume.id),
            "raw_text": resume.raw_text,
            "structured_data": resume.structured_data,
            "original_filename": resume.original_filename,
            "created_at": resume.created_at.isoformat() if resume.created_at else None
        }

    async def get_candidates(
        self,
        org_id: uuid.UUID,
        search_query: Optional[str] = None,
        has_resume: Optional[bool] = None,
        no_roles: Optional[bool] = None
    ) -> list[Dict[str, Any]]:
        """Retrieve all candidates for an organization with their attached jobs and latest scores, with filtering and search support"""
        from ..models.db_models import Job, JobAttachment, Analysis, Resume, Embedding
        from sqlalchemy import or_, exists, and_, case
        import logging

        logger = logging.getLogger(__name__)

        # Define search rank and vector similarity if search_query is provided
        search_rank = None
        query_embedding = None
        max_similarity_subq = None

        if search_query:
            # Simple keyword weighting: Name match > Email match > Location match > Job title match
            search_rank = case(
                (Candidate.name.ilike(f"%{search_query}%"), 4),
                (Candidate.email.ilike(f"%{search_query}%"), 3),
                (Candidate.location.ilike(f"%{search_query}%"), 2),
                else_=0
            ).label("search_rank")

            # Try to get vector similarity for resume content search
            try:
                from src.services.embedding import EmbeddingService
                embedding_service = EmbeddingService()
                query_embedding = await embedding_service.generate_embedding(search_query)
            except Exception as e:
                logger.warning(f"Failed to generate embedding for candidate search: {e}")

        # 1. Build query with filters
        query = select(Candidate).where(Candidate.org_id == org_id)

        # Search filter - keyword search + semantic search on resumes
        if search_query:
            query = query.add_columns(search_rank)

            # For attached job titles, we need to join
            job_title_subquery = (
                select(JobAttachment.candidate_id)
                .join(Job, Job.id == JobAttachment.job_id)
                .where(Job.title.ilike(f"%{search_query}%"))
            )

            keyword_search_filter = or_(
                Candidate.name.ilike(f"%{search_query}%"),
                Candidate.email.ilike(f"%{search_query}%"),
                Candidate.location.ilike(f"%{search_query}%"),
                Candidate.id.in_(job_title_subquery)
            )

            if query_embedding is not None:
                # Subquery to get max similarity per candidate
                from sqlalchemy import func
                max_similarity_subq = (
                    select(
                        Resume.candidate_id,
                        func.max(1 - Embedding.vector.cosine_distance(query_embedding)).label("max_similarity")
                    )
                    .join(Embedding, (Embedding.resume_id == Resume.id) & (Embedding.embedding_type == "full"))
                    .where(Resume.is_optimized == False)
                    .group_by(Resume.candidate_id)
                    .subquery()
                )

                # Add the max_similarity as a column
                query = query.outerjoin(
                    max_similarity_subq,
                    Candidate.id == max_similarity_subq.c.candidate_id
                )
                query = query.add_columns(max_similarity_subq.c.max_similarity)

                # Use OR between keyword search and vector similarity threshold
                query = query.where(or_(keyword_search_filter, max_similarity_subq.c.max_similarity > 0.2))
            else:
                query = query.where(keyword_search_filter)

        # Has resume filter
        if has_resume is not None:
            if has_resume:
                # Only candidates with at least one resume
                resume_exists = exists().where(
                    and_(
                        Resume.candidate_id == Candidate.id,
                        Resume.is_optimized == False  # Only count original resumes
                    )
                )
                query = query.where(resume_exists)
            else:
                # Only candidates with no resumes
                resume_exists = exists().where(
                    and_(
                        Resume.candidate_id == Candidate.id,
                        Resume.is_optimized == False
                    )
                )
                query = query.where(~resume_exists)

        # No roles filter - only candidates with 0 attached jobs
        if no_roles:
            attachment_exists = exists().where(JobAttachment.candidate_id == Candidate.id)
            query = query.where(~attachment_exists)

        # Define ordering: similarity score (if exists) + search rank, then created_at
        order_by_clauses = []
        if search_query:
            if max_similarity_subq is not None:
                # Reference the column from the subquery directly
                from sqlalchemy import func
                # Combined scoring: keyword rank (weighted heavily) + vector similarity
                # This ensures keyword matches always rank higher than pure semantic matches
                order_by_clauses.append((search_rank * 100 + func.coalesce(max_similarity_subq.c.max_similarity, 0)).desc())
            else:
                order_by_clauses.append(search_rank.desc())
            order_by_clauses.append(Candidate.created_at.desc())
        else:
            order_by_clauses.append(Candidate.created_at.desc())

        # Execute query
        result = await self.session.execute(query.order_by(*order_by_clauses))

        # Extract candidates from result
        if search_query:
            # When search columns are added, we need to extract just the Candidate objects
            rows = result.all()
            candidates = [row.Candidate if hasattr(row, 'Candidate') else row[0] for row in rows]
        else:
            candidates = result.scalars().all()

        formatted_candidates = []
        for candidate in candidates:
            # 2. Get attached jobs and their latest analysis score
            attached_query = (
                select(Job, JobAttachment.resume_id)
                .join(JobAttachment, Job.id == JobAttachment.job_id)
                .where(JobAttachment.candidate_id == candidate.id)
            )
            attached_result = await self.session.execute(attached_query)
            attached_rows = attached_result.all()
            
            # Process attached jobs
            attached_jobs = []
            for row in attached_rows:
                job = row.Job
                attached_resume_id = row.resume_id
                
                # Verify job belongs to the same org
                if job.org_id != candidate.org_id:
                    continue

                # Use common status logic
                status_data = await self._get_analysis_status_for_attachment(
                    candidate_id=candidate.id,
                    job_id=job.id,
                    attached_resume_id=attached_resume_id
                )

                attached_jobs.append({
                    "id": str(job.id),
                    "title": job.title,
                    "client_name": job.client_name,
                    "status": "attached",
                    "analysis_status": status_data["analysis_status"],
                    "analysis_score": status_data["analysis_score"],
                    "is_analysis_processing": status_data["is_analysis_processing"],
                    "attached_resume_id": str(attached_resume_id) if attached_resume_id else None
                })

            # Check if candidate has at least one original (non-optimized) resume
            resume_check_query = (
                select(Resume.id)
                .where(Resume.candidate_id == candidate.id)
                .where(Resume.is_optimized == False)
                .limit(1)
            )
            resume_check_result = await self.session.execute(resume_check_query)
            has_resume = resume_check_result.scalar_one_or_none() is not None

            formatted_candidates.append({
                "id": str(candidate.id),
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "location": candidate.location,
                "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
                "attached_jobs": attached_jobs,
                "has_resume": has_resume
            })
            
        return formatted_candidates
    async def get_or_create_candidate_by_name(self, name: str, email: Optional[str] = None, org_id: Optional[uuid.UUID] = None) -> uuid.UUID:
        """Simple get or create by name/email for now"""
        if email:
            query = select(Candidate).where(Candidate.email == email)
            if org_id:
                query = query.where(Candidate.org_id == org_id)
            
            result = await self.session.execute(query.limit(1))
            candidate = result.scalar_one_or_none()
            if candidate:
                return candidate.id
        else:
            # Fallback to name if no email
            query = select(Candidate).where(Candidate.name == name)
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

    async def get_notes(self, candidate_id: uuid.UUID, org_id: Optional[uuid.UUID] = None) -> list[Dict[str, Any]]:
        """Retrieve all notes for a candidate"""
        from ..models.db_models import User, Candidate
        
        query = (
            select(CandidateNote, User.email)
            .join(User, CandidateNote.user_id == User.id)
            .join(Candidate, CandidateNote.candidate_id == Candidate.id)
            .where(CandidateNote.candidate_id == candidate_id)
        )
        
        if org_id:
            query = query.where(Candidate.org_id == org_id)
            
        result = await self.session.execute(
            query.order_by(CandidateNote.created_at.desc())
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
