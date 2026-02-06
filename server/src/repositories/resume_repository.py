import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Resume


class ResumeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_resume(
        self,
        original_filename: str,
        raw_text: str = "",
        structured_data: dict = None,
        embedding: List[float] = None,
        storage_key: Optional[str] = None,
        job_id: Optional[uuid.UUID] = None,
        is_active: bool = True
    ) -> uuid.UUID:
        """Insert a new resume with its embedding"""
        import hashlib
        text_hash = hashlib.sha256(raw_text.encode()).hexdigest() if raw_text else None
        
        resume = Resume(
            original_filename=original_filename,
            raw_text=raw_text,
            raw_text_hash=text_hash,
            structured_data=structured_data or {},
            embedding=embedding,
            storage_key=storage_key,
            job_id=job_id,
            is_active=is_active
        )
        self.session.add(resume)
        await self.session.flush()
        return resume.id

    async def get_resume_by_hash(self, text_hash: str) -> Optional[Dict[str, Any]]:
        """Find resume by raw_text hash"""
        result = await self.session.execute(
            select(Resume)
            .where(Resume.raw_text_hash == text_hash)
            .limit(1)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            return None
        return {
            "id": resume.id,
            "structured_data": resume.structured_data,
            "original_filename": resume.original_filename
        }
    
    async def find_similar_resumes(
        self,
        query_embedding: List[float],
        limit: int = 5,
        exclude_ids: Optional[List[uuid.UUID]] = None
    ) -> List[Dict[str, Any]]:
        """Find resumes similar to the query embedding using cosine similarity"""
        # Using pgvector's cosine distance operator <=>
        # similarity = 1 - distance
        stmt = select(
            Resume,
            (1 - Resume.embedding.cosine_distance(query_embedding)).label("similarity")
        )
        
        if exclude_ids:
            stmt = stmt.where(Resume.id.notin_(exclude_ids))
            
        result = await self.session.execute(
            stmt.order_by(Resume.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        
        rows = result.all()
        return [
            {
                "id": str(row.Resume.id),
                "filename": row.Resume.original_filename,
                "structured_data": row.Resume.structured_data,
                "similarity": float(row.similarity)
            }
            for row in rows
        ]
    
    async def get_resume_by_id(self, resume_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve a resume by ID"""
        result = await self.session.execute(
            select(Resume).where(Resume.id == resume_id)
        )
        resume = result.scalar_one_or_none()
        
        if not resume:
            return None
            
        return {
            "id": str(resume.id),
            "filename": resume.original_filename,
            "raw_text": resume.raw_text,
            "structured_data": resume.structured_data,
            "storage_key": resume.storage_key,
            "job_id": str(resume.job_id) if resume.job_id else None,
            "is_active": resume.is_active,
            "created_at": resume.created_at.isoformat() if resume.created_at else None
        }

    async def get_resumes_by_job_id(self, job_id: uuid.UUID) -> List[Resume]:
        """Retrieve all resumes for a specific job including their analyses"""
        from sqlalchemy.orm import selectinload
        result = await self.session.execute(
            select(Resume)
            .options(selectinload(Resume.analyses))
            .where(Resume.job_id == job_id)
        )
        return result.scalars().all()

    async def has_resumes(self) -> bool:
        """Check if there are any resumes in the database"""
        result = await self.session.execute(select(Resume).limit(1))
        return result.scalar_one_or_none() is not None

    async def get_all_resumes(self) -> List[Dict[str, Any]]:
        """Retrieve all resumes from the database"""
        result = await self.session.execute(
            select(Resume).order_by(Resume.created_at.desc())
        )
        resumes = result.scalars().all()
        return [
            {
                "id": str(resume.id),
                "filename": resume.original_filename,
                "job_id": str(resume.job_id) if resume.job_id else None,
                "is_active": resume.is_active,
                "created_at": resume.created_at.isoformat() if resume.created_at else None
            }
            for resume in resumes
        ]

    async def get_unique_filename(self, filename: str) -> str:
        """
        Checks if a filename already exists in the database.
        If it does, it appends an incrementing suffix (_1, _2, etc.) to the base name.
        """
        import os
        base_name, extension = os.path.splitext(filename)
        
        # Initial check
        result = await self.session.execute(
            select(Resume).where(Resume.original_filename == filename)
        )
        if result.scalar_one_or_none() is None:
            return filename
            
        # If exists, start incrementing
        counter = 1
        while True:
            new_filename = f"{base_name}_{counter}{extension}"
            result = await self.session.execute(
                select(Resume).where(Resume.original_filename == new_filename)
            )
            if result.scalar_one_or_none() is None:
                return new_filename
            counter += 1

    async def delete_resume(self, resume_id: uuid.UUID) -> bool:
        """Delete a resume by ID"""
        result = await self.session.execute(
            select(Resume).where(Resume.id == resume_id)
        )
        resume = result.scalar_one_or_none()
        if resume:
            await self.session.delete(resume)
            await self.session.flush()
            return True
        return False

    async def update_resume(
        self,
        resume_id: uuid.UUID,
        raw_text: Optional[str] = None,
        structured_data: Optional[dict] = None,
        embedding: Optional[List[float]] = None,
        storage_key: Optional[str] = None,
        job_id: Optional[uuid.UUID] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """Update an existing resume's details"""
        result = await self.session.execute(
            select(Resume).where(Resume.id == resume_id)
        )
        resume = result.scalar_one_or_none()
        
        if not resume:
            return False
            
        if raw_text is not None:
            resume.raw_text = raw_text
            import hashlib
            resume.raw_text_hash = hashlib.sha256(raw_text.encode()).hexdigest()
        if structured_data is not None:
            resume.structured_data = structured_data
        if embedding is not None:
            resume.embedding = embedding
        if storage_key is not None:
            resume.storage_key = storage_key
        if job_id is not None:
            resume.job_id = job_id
        if is_active is not None:
            resume.is_active = is_active
            
        await self.session.flush()
        return True
