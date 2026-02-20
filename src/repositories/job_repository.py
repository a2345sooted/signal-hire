import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Job, Resume


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_job(
        self,
        raw_text: str,
        structured_data: dict,
        embedding: Optional[List[float]] = None,
        title: Optional[str] = None,
        markdown_content: Optional[str] = None,
        department: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Insert a new job with its embedding"""
        job = Job(
            title=title,
            raw_text=raw_text,
            markdown_content=markdown_content,
            department=department,
            structured_data=structured_data,
            embedding=embedding,
            org_id=org_id
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
        department: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Insert a new job with a specific ID"""
        job = Job(
            id=job_id,
            title=title,
            raw_text=raw_text,
            markdown_content=markdown_content,
            department=department,
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
        structured_data: Optional[dict] = None,
        embedding: Optional[List[float]] = None,
        markdown_content: Optional[str] = None,
        department: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None
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
        if structured_data is not None:
            job.structured_data = structured_data
        if embedding is not None:
            job.embedding = embedding
        if markdown_content is not None:
            job.markdown_content = markdown_content
        if department is not None:
            job.department = department
        if org_id is not None:
            job.org_id = org_id
            
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
            
        return {
            "id": str(job.id),
            "org_id": str(job.org_id) if job.org_id else None,
            "title": job.title,
            "raw_text": job.raw_text,
            "markdown_content": job.markdown_content,
            "department": job.department,
            "structured_data": job.structured_data,
            "embedding": job.embedding,
            "created_at": job.created_at
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
                "raw_text": job.raw_text,
                "markdown_content": job.markdown_content,
                "department": job.department,
                "structured_data": job.structured_data,
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
