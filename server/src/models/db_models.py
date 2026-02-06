import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from sqlalchemy.orm import relationship

from ..database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_filename = Column(String(255), nullable=False)
    storage_key = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    raw_text_hash = Column(String(64), nullable=True)
    structured_data = Column(JSONB, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("Job", back_populates="resumes")
    analyses = relationship("Analysis", back_populates="resume", cascade="all, delete-orphan", order_by="Analysis.created_at.desc()")

    __table_args__ = (
        Index('ix_resumes_raw_text_hash', 'raw_text_hash'),
    )

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    markdown_content = Column(Text, nullable=True)
    department = Column(String(255), nullable=True)
    structured_data = Column(JSONB, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    resumes = relationship("Resume", back_populates="job", cascade="all, delete-orphan")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False)
    content = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    resume = relationship("Resume", back_populates="analyses")
