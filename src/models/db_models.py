import uuid
from datetime import datetime, timezone

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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organizations = relationship("OrganizationUser", back_populates="user")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    users = relationship("OrganizationUser", back_populates="organization")
    invites = relationship("OrganizationInvite", back_populates="organization", cascade="all, delete-orphan")


class OrganizationUser(Base):
    __tablename__ = "organization_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(OrgRole), nullable=False, default=OrgRole.RECRUITER)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="users")
    user = relationship("User", back_populates="organizations")


class OrganizationInvite(Base):
    __tablename__ = "organization_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(Enum(OrgRole), nullable=False, default=OrgRole.RECRUITER)
    inviter_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_email = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="invites")
    inviter = relationship("User")


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    
    # New fields
    phone = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)
    citizenship = Column(String(255), nullable=True)
    linkedin_url = Column(String(255), nullable=True)
    engagement_types = Column(JSONB, nullable=True)  # List of engagement types: fte, c2c, w2
    work_preference = Column(JSONB, nullable=True)  # List of work preferences: remote, hybrid, in-office
    open_to_relocation = Column(Boolean, nullable=True, default=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    resumes = relationship("Resume", back_populates="candidate", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="candidate", cascade="all, delete-orphan")
    notes = relationship("CandidateNote", back_populates="candidate", cascade="all, delete-orphan")
    attached_jobs = relationship("JobAttachment", back_populates="candidate", cascade="all, delete-orphan")
    recommended_jobs = relationship("JobRecommendation", back_populates="candidate", cascade="all, delete-orphan")
    candidate_recommendations = relationship("CandidateRecommendation", back_populates="candidate", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="candidate", cascade="all, delete-orphan")


class CandidateNote(Base):
    __tablename__ = "candidate_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # is_current is deprecated and should not be used
    is_current = Column(Boolean, nullable=False, default=True)
    is_generated = Column(Boolean, nullable=False, default=False)
    is_optimized = Column(Boolean, nullable=False, default=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    diff = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="resumes")
    candidate = relationship("Candidate", back_populates="resumes")
    parent = relationship("Resume", remote_side=[id], backref="children")
    analyses = relationship("Analysis", back_populates="resume", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="resume", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_resumes_raw_text_hash', 'raw_text_hash'),
    )

class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=True)
    client_name = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=True)
    markdown_content = Column(Text, nullable=True)
    structured_data = Column(JSONB, nullable=True)
    details = Column(JSONB, nullable=True)
    
    # New fields
    location = Column(String(255), nullable=True)
    work_arrangement = Column(String(50), nullable=True)  # in-office, hybrid, remote
    hybrid_days_per_week = Column(Integer, nullable=True)
    pay_range_min = Column(Integer, nullable=True)
    pay_range_max = Column(Integer, nullable=True)
    pay_type = Column(String(50), nullable=True)  # salary, hourly
    employment_type = Column(String(50), nullable=True)  # fte, w2, contract
    offers_relocation = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    resumes = relationship("Resume", back_populates="job", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="job", cascade="all, delete-orphan")
    notes = relationship("JobNote", back_populates="job", cascade="all, delete-orphan")
    attached_candidates = relationship("JobAttachment", back_populates="job", cascade="all, delete-orphan")
    recommended_candidates = relationship("JobRecommendation", back_populates="job", cascade="all, delete-orphan")
    candidate_recommendations = relationship("CandidateRecommendation", back_populates="job", cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="job", cascade="all, delete-orphan")

class JobAttachment(Base):
    __tablename__ = "job_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="attached_candidates")
    candidate = relationship("Candidate", back_populates="attached_jobs")
    resume = relationship("Resume")

class JobRecommendation(Base):
    __tablename__ = "job_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=True)  # Match score
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="recommended_candidates")
    candidate = relationship("Candidate", back_populates="recommended_jobs")

class CandidateRecommendation(Base):
    __tablename__ = "candidate_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=True)  # Match score
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    candidate = relationship("Candidate", back_populates="candidate_recommendations")
    job = relationship("Job", back_populates="candidate_recommendations")

class JobNote(Base):
    __tablename__ = "job_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="notes")
    user = relationship("User")

class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=True)
    content = Column(JSONB, nullable=False)
    jd_hash = Column(Text, nullable=True)
    details_hash = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    candidate = relationship("Candidate", back_populates="analyses")
    job = relationship("Job", back_populates="analyses")
    resume = relationship("Resume", back_populates="analyses")
    
class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=True)
    embedding_type = Column(String(50), nullable=False)
    vector = Column(Vector(1536), nullable=False)
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    job = relationship("Job", back_populates="embeddings")
    candidate = relationship("Candidate", back_populates="embeddings")
    resume = relationship("Resume", back_populates="embeddings")

class ProcessingTask(Base):
    __tablename__ = "processing_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_type = Column(String(50), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=True)
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    job = relationship("Job")
    candidate = relationship("Candidate")
    resume = relationship("Resume")

