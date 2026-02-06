import uuid
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..models.db_models import Analysis


class AnalysisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_analysis(
        self,
        resume_id: uuid.UUID,
        content: dict
    ) -> uuid.UUID:
        """Insert a new analysis"""
        analysis = Analysis(
            resume_id=resume_id,
            content=content
        )
        self.session.add(analysis)
        await self.session.flush()
        return analysis.id

    async def get_analysis_by_id(self, analysis_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve an analysis by ID"""
        result = await self.session.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            return None
            
        return {
            "id": str(analysis.id),
            "resume_id": str(analysis.resume_id),
            "content": analysis.content,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None
        }

    async def get_analysis_for_resume(self, resume_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve analysis for a specific resume"""
        result = await self.session.execute(
            select(Analysis).where(Analysis.resume_id == resume_id).order_by(Analysis.created_at.desc()).limit(1)
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            return None
            
        return {
            "id": str(analysis.id),
            "resume_id": str(analysis.resume_id),
            "content": analysis.content,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None
        }

    async def get_analysis_by_resume(self, resume_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieve analysis for a specific resume"""
        result = await self.session.execute(
            select(Analysis)
            .where(Analysis.resume_id == resume_id)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        analysis = result.scalar_one_or_none()
        
        if not analysis:
            return None
            
        return {
            "id": str(analysis.id),
            "resume_id": str(analysis.resume_id),
            "content": analysis.content,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None
        }
