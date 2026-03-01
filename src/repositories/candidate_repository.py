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

    async def get_candidate_by_id(self, candidate_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve a candidate by ID along with their attached jobs and notes"""
        from ..models.db_models import Job, JobAttachment, CandidateRecommendation, Analysis
        from ..agents.resume_processor.run import is_resume_processing_active

        result = await self.session.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        
        if not candidate:
            return None
        
        # Get attached jobs
        from ..models.db_models import Job, JobAttachment
        attached_query = (
            select(Job, JobAttachment.resume_id)
            .join(JobAttachment, Job.id == JobAttachment.job_id)
            .where(JobAttachment.candidate_id == candidate_id)
        )
        attached_result = await self.session.execute(attached_query)
        attached_rows = attached_result.all()

        # Get recommended jobs
        recommended_query = select(Job).join(CandidateRecommendation).where(CandidateRecommendation.candidate_id == candidate_id)
        recommended_result = await self.session.execute(recommended_query)
        recommended_jobs = recommended_result.scalars().all()

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
        notes = await self.get_notes(candidate_id)

        # Build attached_jobs with analysis status
        from ..agents.analyzer.run import is_analysis_active
        formatted_attached_jobs = []
        for row in attached_rows:
            job = row.Job
            attached_resume_id = row.resume_id

            # Check for analysis in DB
            analysis_stmt = (
                select(Analysis)
                .where(Analysis.candidate_id == candidate_id)
                .where(Analysis.job_id == job.id)
            )
            
            # If we have a specific resume attached, look for analysis with that resume
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

            # Get the latest task (active or not) to compare with analysis
            from ..models.db_models import ProcessingTask
            from ..constants import TASK_ANALYSIS
            from datetime import datetime, timezone, timedelta
            
            task_stmt = (
                select(ProcessingTask)
                .where(ProcessingTask.job_id == job.id)
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
                    # If we have a ready analysis, we ONLY consider it processing if the task
                    # is SIGNIFICANTLY newer than the analysis completion (to avoid race conditions).
                    if not is_ready:
                        is_processing = True
                    else:
                        analysis_updated_at = analysis.updated_at or analysis.created_at
                        if analysis_updated_at.tzinfo is None:
                            analysis_updated_at = analysis_updated_at.replace(tzinfo=timezone.utc)
                        
                        # Use a small buffer (e.g., 5 seconds) to ensure that we don't 
                        # show "processing" for a task that actually finished just now
                        # but hasn't been deleted yet.
                        if task_time > (analysis_updated_at + timedelta(seconds=5)):
                            is_processing = True

            analysis_status = "processing" if is_processing else ("ready" if is_ready else "pending")
            
            # Final decision for UI processing flag
            display_processing = is_processing

            formatted_attached_jobs.append({
                "id": str(job.id),
                "title": job.title,
                "status": "attached",
                "analysis_status": analysis_status,
                "analysis_score": score,
                "is_analysis_processing": display_processing,
                "attached_resume_id": str(attached_resume_id) if attached_resume_id else None
            })

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
            "recommended_jobs": [
                {
                    "id": str(job.id),
                    "title": job.title,
                    "status": "recommended"
                }
                for job in recommended_jobs
            ],
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

    async def get_candidates(self, org_id: uuid.UUID) -> list[Dict[str, Any]]:
        """Retrieve all candidates for an organization with their attached jobs and latest scores"""
        from ..models.db_models import Job, JobAttachment, Analysis
        
        # 1. Fetch basic candidate info
        result = await self.session.execute(
            select(Candidate).where(Candidate.org_id == org_id).order_by(Candidate.created_at.desc())
        )
        candidates = result.scalars().all()
        
        formatted_candidates = []
        for candidate in candidates:
            # 2. Get attached jobs and their latest analysis score
            attached_query = (
                select(Job.id, Job.title, Analysis.content)
                .join(JobAttachment, Job.id == JobAttachment.job_id)
                .outerjoin(Analysis, (Analysis.job_id == Job.id) & (Analysis.candidate_id == candidate.id))
                .where(JobAttachment.candidate_id == candidate.id)
                .order_by(Analysis.created_at.desc())
            )
            attached_result = await self.session.execute(attached_query)
            attached_rows = attached_result.all()
            
            # Process attached jobs to get unique jobs with their latest score
            seen_jobs = set()
            attached_jobs = []
            for row in attached_rows:
                if row.id in seen_jobs:
                    continue
                seen_jobs.add(row.id)
                
                score = row.content.get("score") if row.content else None
                attached_jobs.append({
                    "id": str(row.id),
                    "title": row.title,
                    "score": score
                })
            
            formatted_candidates.append({
                "id": str(candidate.id),
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "location": candidate.location,
                "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
                "attached_jobs": attached_jobs
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
