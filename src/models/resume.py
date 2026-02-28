from typing import List, Optional

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: Optional[str] = Field(..., description="The full name of the person")
    email: Optional[str] = Field(..., description="The email address")
    phone: Optional[str] = Field(..., description="The phone number")
    location: Optional[str] = Field(..., description="The location (city, state, etc.)")
    linkedin: Optional[str] = Field(..., description="LinkedIn profile URL")

class Experience(BaseModel):
    company: Optional[str] = Field(..., description="The name of the company")
    title: Optional[str] = Field(..., description="The job title")
    dates: Optional[str] = Field(..., description="The dates of employment")
    bullets: List[str] = Field(..., description="Key responsibilities and achievements")

class Education(BaseModel):
    school: Optional[str] = Field(..., description="The name of the school or university")
    degree: Optional[str] = Field(..., description="The degree obtained")
    dates: Optional[str] = Field(..., description="The dates of attendance")

class Project(BaseModel):
    name: Optional[str] = Field(..., description="Project name")
    description: Optional[str] = Field(..., description="Project description")
    technologies: List[str] = Field(..., description="Technologies used")
    links: List[str] = Field(..., description="GitHub or demo URLs")

class BulletRewrite(BaseModel):
    original_bullet: str = Field(..., description="The original bullet point from the resume")
    suggestion: str = Field(..., description="The suggested rewrite or improvement")

class OptimizationPlanSchema(BaseModel):
    bullets_to_rewrite: List[BulletRewrite] = Field(..., description="Specific experience bullets to strengthen, with suggestions")
    skills_to_emphasize: List[str] = Field(..., description="Existing skills that should be more prominent")
    skills_to_add: List[str] = Field(..., description="Skills mentioned in job but missing from resume")
    keywords_to_include: List[str] = Field(..., description="ATS keywords to integrate")
    gaps_identified: List[str] = Field(..., description="Major gaps between resume and job requirements")
    strong_sections: List[str] = Field(..., description="Sections of the resume that already match well")

class ReviewFeedbackSchema(BaseModel):
    ats_keyword_coverage: float = Field(..., description="Percentage of key ATS keywords present (0.0 to 1.0)")
    consistency_check: str = Field(..., description="Analysis of consistency and accuracy vs original resume")
    grammar_quality: str = Field(..., description="Evaluation of grammar, spelling, and formatting")
    tone_appropriateness: str = Field(..., description="Assessment of tone for the seniority level")
    remaining_gaps: List[str] = Field(..., description="Any significant gaps still remaining vs job description")
    major_issues_found: bool = Field(..., description="Whether major issues were found that need manual correction")
    overall_score: int = Field(..., description="Overall quality score (1-10)")

class ResumeSchema(BaseModel):
    contact: Contact = Field(..., description="Contact information")
    summary: Optional[str] = Field(..., description="A brief summary of the professional profile")
    experience: List[Experience] = Field(..., description="Work history")
    education: List[Education] = Field(..., description="Educational background")
    skills: List[str] = Field(..., description="List of skills")
    projects: List[Project] = Field(..., description="Personal or side projects")
    ai_projects: List[Project] = Field(..., description="AI-specific projects")
    military_service: Optional[str] = Field(..., description="Military service history")
    interests: List[str] = Field(..., description="Personal interests, hobbies, certifications")
    
    # New fields for candidate matching
    citizenship: Optional[str] = Field(None, description="Citizenship or work authorization status")
    engagement_types: List[str] = Field(default_factory=list, description="Engagement types preferred: fte, c2c, w2")
    work_preference: List[str] = Field(default_factory=list, description="Work preferences: remote, hybrid, in-office")
    open_to_relocation: bool = Field(False, description="Whether the candidate is open to relocation")

class UserNoteUpdate(BaseModel):
    content: str = Field(..., description="The updated or new factual note")
    note_id: Optional[str] = Field(None, description="The ID of the existing note to update, if applicable")

class UserNoteExtractionSchema(BaseModel):
    notes: List[UserNoteUpdate] = Field(..., description="List of key facts, skills, and experiences extracted from the text")

class UserNoteSchema(BaseModel):
    notes: List[str] = Field(..., description="List of key facts, skills, and experiences extracted from the text")
