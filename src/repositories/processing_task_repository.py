import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from ..models.db_models import ProcessingTask

class ProcessingTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_task(
        self,
        task_id: uuid.UUID,
        task_type: str,
        job_id: Optional[uuid.UUID] = None,
        candidate_id: Optional[uuid.UUID] = None,
        resume_id: Optional[uuid.UUID] = None,
        status: str = "starting"
    ) -> uuid.UUID:
        # Check if a task with the same ID already exists
        result = await self.session.execute(
            select(ProcessingTask).where(ProcessingTask.id == task_id)
        )
        task = result.scalar_one_or_none()

        if task:
            # Update existing task
            task.task_type = task_type
            task.job_id = job_id
            task.candidate_id = candidate_id
            task.resume_id = resume_id
            task.status = status
            task.error_message = None
            task.updated_at = datetime.now(timezone.utc) # Note: datetime needs to be imported or use sqlalchemy func
        else:
            task = ProcessingTask(
                id=task_id,
                task_type=task_type,
                job_id=job_id,
                candidate_id=candidate_id,
                resume_id=resume_id,
                status=status
            )
            self.session.add(task)
        
        await self.session.flush()
        return task.id

    async def update_task(
        self,
        task_id: uuid.UUID,
        status: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        result = await self.session.execute(
            select(ProcessingTask).where(ProcessingTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return False
        
        if status:
            task.status = status
        if error_message is not None:
            task.error_message = error_message
        
        await self.session.flush()
        return True

    async def delete_task(self, task_id: uuid.UUID) -> bool:
        await self.session.execute(
            delete(ProcessingTask).where(ProcessingTask.id == task_id)
        )
        await self.session.flush()
        return True

    async def cancel_tasks_by_resume_id(self, resume_id: uuid.UUID) -> int:
        """Update tasks for a resume to 'cancelled'"""
        stmt = (
            delete(ProcessingTask)
            .where(ProcessingTask.resume_id == resume_id)
            .where(ProcessingTask.status.in_(["starting", "processing"]))
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def is_task_active(
        self,
        task_type: Optional[str] = None,
        job_id: Optional[uuid.UUID] = None,
        candidate_id: Optional[uuid.UUID] = None,
        resume_id: Optional[uuid.UUID] = None,
        timeout_minutes: int = 10
    ) -> bool:
        stmt = select(ProcessingTask).where(ProcessingTask.status.in_(["starting", "processing"]))
        
        if task_type:
            stmt = stmt.where(ProcessingTask.task_type == task_type)
        if job_id:
            stmt = stmt.where(ProcessingTask.job_id == job_id)
        if candidate_id:
            stmt = stmt.where(ProcessingTask.candidate_id == candidate_id)
        if resume_id:
            stmt = stmt.where(ProcessingTask.resume_id == resume_id)
        
        result = await self.session.execute(stmt)
        tasks = result.scalars().all()
        
        if not tasks:
            return False
            
        # Check for stuck tasks and filter them out
        active_found = False
        now = datetime.now(timezone.utc)
        for task in tasks:
            # If task is older than timeout, it's considered stuck/inactive
            # updated_at might be None if just created, so fallback to created_at
            last_activity = task.updated_at or task.created_at
            if (now - last_activity).total_seconds() / 60 < timeout_minutes:
                active_found = True
                break
        
        return active_found
