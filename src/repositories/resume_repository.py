import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Resume, Embedding


class ResumeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
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

    async def create_resume(
        self,
        original_filename: str,
        raw_text: str = "",
        structured_data: dict = None,
        embedding: List[float] = None,
        storage_key: Optional[str] = None,
        job_id: Optional[uuid.UUID] = None,
        candidate_id: Optional[uuid.UUID] = None,
        is_active: bool = True,
        is_generated: bool = False,
        is_optimized: bool = False,
        parent_id: Optional[uuid.UUID] = None,
        diff: Optional[dict] = None
    ) -> uuid.UUID:
        """Insert a new resume with its embedding"""
        import hashlib
        text_hash = hashlib.sha256(raw_text.encode()).hexdigest() if raw_text else None
        
        resume = Resume(
            original_filename=original_filename,
            raw_text=raw_text,
            raw_text_hash=text_hash,
            structured_data=structured_data or {},
            storage_key=storage_key,
            job_id=job_id,
            candidate_id=candidate_id,
            is_active=is_active,
            is_generated=is_generated,
            is_optimized=is_optimized,
            parent_id=parent_id,
            diff=diff
        )
        self.session.add(resume)
        await self.session.flush()

        if embedding:
            emb = Embedding(
                resume_id=resume.id,
                candidate_id=candidate_id,
                embedding_type="full",
                vector=embedding
            )
            self.session.add(emb)
            await self.session.flush()

        return resume.id

    async def create_resume_with_id(
        self,
        resume_id: uuid.UUID,
        original_filename: str,
        raw_text: str = "",
        structured_data: dict = None,
        embedding: List[float] = None,
        storage_key: Optional[str] = None,
        job_id: Optional[uuid.UUID] = None,
        candidate_id: Optional[uuid.UUID] = None,
        is_active: bool = True,
        is_generated: bool = False,
        is_optimized: bool = False,
        parent_id: Optional[uuid.UUID] = None,
        diff: Optional[dict] = None
    ) -> uuid.UUID:
        """Insert a new resume with a pre-generated ID"""
        import hashlib
        text_hash = hashlib.sha256(raw_text.encode()).hexdigest() if raw_text else None
        
        resume = Resume(
            id=resume_id,
            original_filename=original_filename,
            raw_text=raw_text,
            raw_text_hash=text_hash,
            structured_data=structured_data or {},
            storage_key=storage_key,
            job_id=job_id,
            candidate_id=candidate_id,
            is_active=is_active,
            is_generated=is_generated,
            is_optimized=is_optimized,
            parent_id=parent_id,
            diff=diff
        )
        self.session.add(resume)
        await self.session.flush()

        if embedding:
            emb = Embedding(
                resume_id=resume.id,
                candidate_id=candidate_id,
                embedding_type="full",
                vector=embedding
            )
            self.session.add(emb)
            await self.session.flush()

        return resume.id

    async def get_resume_by_hash(self, text_hash: str, org_id: Optional[uuid.UUID] = None) -> Optional[Dict[str, Any]]:
        """Find resume by raw_text hash, optionally filtered by organization"""
        from ..models.db_models import Candidate
        
        stmt = select(Resume).where(Resume.raw_text_hash == text_hash)
        
        if org_id:
            stmt = stmt.join(Candidate, Resume.candidate_id == Candidate.id).where(Candidate.org_id == org_id)
            
        result = await self.session.execute(stmt.limit(1))
        resume = result.scalar_one_or_none()
        if not resume:
            return None
        return {
            "id": resume.id,
            "candidate_id": resume.candidate_id,
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
        stmt = (
            select(
                Resume,
                (1 - Embedding.vector.cosine_distance(query_embedding)).label("similarity")
            )
            .join(Embedding, Embedding.resume_id == Resume.id)
            .where(Embedding.embedding_type == "full")
        )
        
        if exclude_ids:
            stmt = stmt.where(Resume.id.notin_(exclude_ids))
            
        result = await self.session.execute(
            stmt.order_by(Embedding.vector.cosine_distance(query_embedding))
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
            
        # Get embeddings
        from ..models.db_models import Embedding
        emb_result = await self.session.execute(
            select(Embedding)
            .where(Embedding.resume_id == resume_id, Embedding.embedding_type == "full")
            .order_by(Embedding.created_at.desc())
        )
        resume_embedding = emb_result.scalars().first()

        return {
            "id": str(resume.id),
            "filename": resume.original_filename,
            "raw_text": resume.raw_text,
            "structured_data": resume.structured_data,
            "embedding": resume_embedding.vector if resume_embedding else None,
            "storage_key": resume.storage_key,
            "job_id": str(resume.job_id) if resume.job_id else None,
            "candidate_id": str(resume.candidate_id) if resume.candidate_id else None,
            "is_active": resume.is_active,
            "is_optimized": resume.is_optimized,
            "parent_id": str(resume.parent_id) if resume.parent_id else None,
            "diff": resume.diff,
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
            select(Resume).where(Resume.original_filename == filename).limit(1)
        )
        if result.scalar_one_or_none() is None:
            return filename
            
        # If exists, start incrementing
        counter = 1
        while True:
            new_filename = f"{base_name}_{counter}{extension}"
            result = await self.session.execute(
                select(Resume).where(Resume.original_filename == new_filename).limit(1)
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
        candidate_id: Optional[uuid.UUID] = None,
        is_active: Optional[bool] = None,
        is_generated: Optional[bool] = None,
        is_optimized: Optional[bool] = None,
        parent_id: Optional[uuid.UUID] = None,
        diff: Optional[dict] = None
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
            from sqlalchemy import delete
            await self.session.execute(
                delete(Embedding).where(Embedding.resume_id == resume_id, Embedding.embedding_type == "full")
            )
            emb = Embedding(
                resume_id=resume_id,
                candidate_id=resume.candidate_id,
                embedding_type="full",
                vector=embedding
            )
            self.session.add(emb)
        if storage_key is not None:
            resume.storage_key = storage_key
        if job_id is not None:
            resume.job_id = job_id
        if candidate_id is not None:
            resume.candidate_id = candidate_id
        if is_active is not None:
            resume.is_active = is_active
        if is_generated is not None:
            resume.is_generated = is_generated
        if is_optimized is not None:
            resume.is_optimized = is_optimized
        if parent_id is not None:
            resume.parent_id = parent_id
        if diff is not None:
            resume.diff = diff
            
        await self.session.flush()
        return True

    async def get_resumes_by_candidate_id(self, candidate_id: uuid.UUID) -> List[Resume]:
        """Retrieve all resumes for a specific candidate"""
        result = await self.session.execute(
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .order_by(Resume.created_at.desc())
        )
        return result.scalars().all()

    async def get_original_resume_by_candidate_id(self, candidate_id: uuid.UUID) -> Optional[Resume]:
        """Retrieve the single original (non-optimized) resume for a specific candidate"""
        result = await self.session.execute(
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .where(Resume.is_optimized == False)
            .limit(1)
        )
        return result.scalar_one_or_none()
