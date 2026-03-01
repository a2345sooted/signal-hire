import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..database import AsyncSessionLocal
from ..models.db_models import ProcessingTask, Job, Resume, Analysis
from ..repositories.processing_task_repository import ProcessingTaskRepository
from ..repositories.job_repository import JobRepository
from ..repositories.resume_repository import ResumeRepository
from ..repositories.analysis_repository import AnalysisRepository

# Import agent runners
from ..agents.jd_processor.run import run_jd_agent
from ..agents.resume_processor.run import run_resume_agent
from ..agents.analyzer.run import run_analyzer_agent
from ..agents.optimizer.run import run_optimizer_agent

logger = logging.getLogger(__name__)

class TaskRecoveryService:
    def __init__(self, interval_seconds: int = 60, stuck_threshold_minutes: int = 10):
        self.interval_seconds = interval_seconds
        self.stuck_threshold_minutes = stuck_threshold_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"TaskRecoveryService started (interval: {self.interval_seconds}s, threshold: {self.stuck_threshold_minutes}m)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TaskRecoveryService stopped")

    async def _run_loop(self):
        # Initial delay to let the app settle
        await asyncio.sleep(10)
        while self._running:
            try:
                await self.recover_stuck_tasks()
            except Exception as e:
                logger.error(f"Error in TaskRecoveryService loop: {str(e)}", exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def recover_stuck_tasks(self):
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            threshold = now - timedelta(minutes=self.stuck_threshold_minutes)
            
            # Find tasks stuck in 'starting' or 'processing'
            stmt = select(ProcessingTask).where(
                ProcessingTask.status.in_(["starting", "processing"]),
                ProcessingTask.updated_at < threshold
            )
            result = await session.execute(stmt)
            stuck_tasks = result.scalars().all()
            
            if not stuck_tasks:
                return

            logger.info(f"Found {len(stuck_tasks)} stuck tasks for recovery")
            
            for task in stuck_tasks:
                try:
                    await self._recover_task(session, task)
                except Exception as e:
                    logger.error(f"Failed to recover task {task.id} (type: {task.task_type}): {str(e)}", exc_info=True)

    async def _recover_task(self, session: AsyncSession, task: ProcessingTask):
        logger.info(f"Recovering task {task.id} (type: {task.task_type}, job: {task.job_id})")
        
        # Update updated_at to prevent other workers (if any) from picking it up immediately
        task.updated_at = datetime.now(timezone.utc)
        await session.commit()

        if task.task_type == "jd":
            await self._recover_jd_task(session, task)
        elif task.task_type == "resume":
            await self._recover_resume_task(session, task)
        elif task.task_type == "analysis":
            await self._recover_analysis_task(session, task)
        elif task.task_type == "optimizer":
            await self._recover_optimizer_task(session, task)
        else:
            logger.warning(f"Unknown task type for recovery: {task.task_type}")

    async def _recover_jd_task(self, session: AsyncSession, task: ProcessingTask):
        if not task.job_id:
            logger.error(f"JD task {task.id} missing job_id")
            return
            
        job_repo = JobRepository(session)
        job = await job_repo.get_job_by_id(task.job_id)
        if not job or not job.get("raw_text"):
            logger.error(f"Job {task.job_id} or raw_text not found for JD task {task.id}")
            return

        # Trigger JD agent
        asyncio.create_task(run_jd_agent(
            raw_text=job["raw_text"],
            job_id=task.job_id,
            org_id=job.get("org_id")
        ))

    async def _recover_resume_task(self, session: AsyncSession, task: ProcessingTask):
        if not task.resume_id:
            logger.error(f"Resume task {task.id} missing resume_id")
            return
            
        resume_repo = ResumeRepository(session)
        resume_obj = await resume_repo.get_resume_by_id(task.resume_id)
        if not resume_obj:
            logger.error(f"Resume {task.resume_id} not found for recovery")
            return
            
        # Trigger resume agent
        asyncio.create_task(run_resume_agent(
            file_key=resume_obj.storage_key,
            original_filename=resume_obj.original_filename,
            job_id=task.job_id,
            resume_id=task.resume_id,
            org_id=resume_obj.org_id if hasattr(resume_obj, 'org_id') else None,
            raw_text=resume_obj.raw_text
        ))

    async def _recover_analysis_task(self, session: AsyncSession, task: ProcessingTask):
        if not task.job_id or not task.candidate_id or not task.resume_id:
            logger.error(f"Analysis task {task.id} missing required IDs")
            return
            
        job_repo = JobRepository(session)
        job = await job_repo.get_job_by_id(task.job_id)
        
        resume_repo = ResumeRepository(session)
        resume_obj = await resume_repo.get_resume_by_id(task.resume_id)
        
        if not job or not resume_obj:
            logger.error(f"Job or Resume not found for analysis task {task.id}")
            return

        from ..repositories.candidate_repository import CandidateRepository
        candidate_repo = CandidateRepository(session)
        candidate_notes = await candidate_repo.get_notes(task.candidate_id)
        
        # We need the candidate model to get location
        from ..models.db_models import Candidate
        result = await session.execute(select(Candidate).where(Candidate.id == task.candidate_id))
        candidate = result.scalar_one_or_none()
        candidate_location = candidate.location if candidate else None
            
        # Trigger analyzer agent
        asyncio.create_task(run_analyzer_agent(
            job_id=task.job_id,
            candidate_id=task.candidate_id,
            job_data=job,
            resume_data={
                "raw_text": resume_obj.raw_text,
                "structured_data": resume_obj.structured_data,
                "resume_id": str(task.resume_id)
            },
            candidate_notes=candidate_notes,
            candidate_location=candidate_location,
            org_id=job.get("org_id")
        ))

    async def _recover_optimizer_task(self, session: AsyncSession, task: ProcessingTask):
        if not task.job_id or not task.candidate_id or not task.resume_id:
            logger.error(f"Optimizer task {task.id} missing required IDs")
            return
            
        job_repo = JobRepository(session)
        job = await job_repo.get_job_by_id(task.job_id)
        
        resume_repo = ResumeRepository(session)
        resume_obj = await resume_repo.get_resume_by_id(task.resume_id)
        
        analysis_repo = AnalysisRepository(session)
        analysis_data = await analysis_repo.get_analysis_for_candidate_job_resume(
            candidate_id=task.candidate_id,
            job_id=task.job_id,
            resume_id=task.resume_id
        )
        
        if not job or not resume_obj or not analysis_data:
            logger.error(f"Required data not found for optimizer task {task.id}")
            return
            
        # Trigger optimizer agent
        asyncio.create_task(run_optimizer_agent(
            job_id=task.job_id,
            candidate_id=task.candidate_id,
            resume_id=task.resume_id,
            job_data=job,
            resume_data={
                "raw_text": resume_obj.raw_text,
                "structured_data": resume_obj.structured_data,
                "resume_id": str(task.resume_id)
            },
            analysis_data=analysis_data,
            org_id=job.get("org_id")
        ))

# Singleton instance
task_recovery_service = TaskRecoveryService()
