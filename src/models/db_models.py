import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, Index, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum

from sqlalchemy.orm import relationship

from ..database import Base


class OrgRole(enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    RECRUITER = "RECRUITER"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sub = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    organizations = relationship("OrganizationUser", back_populates="user")
    terms_accepted = relationship("UserTerms", back_populates="user", cascade="all, delete-orphan")


class UserTerms(Base):
    __tablename__ = "user_terms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    version = Column(String(50), nullable=False)
    accepted_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    user = relationship("User", back_populates="terms_accepted")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("OrganizationUser", back_populates="organization")


class OrganizationUser(Base):
    __tablename__ = "organization_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(OrgRole), nullable=False, default=OrgRole.RECRUITER)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = relationship("Organization", back_populates="users")
    user = relationship("User", back_populates="organizations")


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="candidate", cascade="all, delete-orphan")
    notes = relationship("CandidateNote", back_populates="candidate", cascade="all, delete-orphan")


class CandidateNote(Base):
    __tablename__ = "candidate_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="notes")
    user = relationship("User")


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
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("Job", back_populates="resumes")
    candidate = relationship("Candidate", back_populates="resumes")
    analyses = relationship("Analysis", back_populates="resume", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_resumes_raw_text_hash', 'raw_text_hash'),
    )

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    markdown_content = Column(Text, nullable=True)
    structured_data = Column(JSONB, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    
    # New fields
    location = Column(String(255), nullable=True)
    work_arrangement = Column(String(50), nullable=True)  # in-office, hybrid, remote
    hybrid_days_per_week = Column(Integer, nullable=True)
    pay_range_min = Column(Integer, nullable=True)
    pay_range_max = Column(Integer, nullable=True)
    pay_type = Column(String(50), nullable=True)  # salary, hourly
    employment_type = Column(String(50), nullable=True)  # fte, w2, contract
    offers_relocation = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    resumes = relationship("Resume", back_populates="job", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="job", cascade="all, delete-orphan")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=True)
    content = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="analyses")
    job = relationship("Job", back_populates="analyses")
    resume = relationship("Resume", back_populates="analyses")
