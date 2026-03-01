from typing import List, Optional, Dict

from pydantic import BaseModel, Field


class JobAnalysisSchema(BaseModel):
    key_skills: List[str] = Field(..., description="Key required skills and technologies")
    experience_level: str = Field(..., description="Experience level expectations (e.g., Senior, Principal, Director)")
    must_haves: List[str] = Field(..., description="Must-have qualifications")
    nice_to_haves: List[str] = Field(..., description="Nice-to-have qualifications")
    ats_keywords: List[str] = Field(..., description="Important keywords for ATS optimization")

class JobSchema(BaseModel):
    company: Optional[str] = Field(..., description="The name of the company")
    title: Optional[str] = Field(..., description="The job title")
    raw_text: str = Field(..., description="The full job description text")
    requirements: Optional[Dict[str, str]] = Field(..., description="Parsed requirements (structured like responsibilities, must_have, etc.)")
    skills: List[str] = Field(..., description="Extracted required skills")
    analysis: Optional[JobAnalysisSchema] = Field(..., description="Deep analysis of the job requirements")

class JobDetailsSchema(BaseModel):
    pay_range_min: Optional[int] = Field(None, description="Minimum pay in USD")
    pay_range_max: Optional[int] = Field(None, description="Maximum pay in USD")
    pay_type: Optional[str] = Field(None, description="salary or hourly")
    employment_type: List[str] = Field(default_factory=list, description="fte, c2c, w2")
    location: Optional[str] = Field(None, description="City, State or 'Remote'")
    arrangement: Optional[str] = Field(None, description="on-site, remote, hybrid")
    hybrid_days_week: Optional[int] = Field(None, description="Number of days per week in office (only if arrangement is hybrid)")
    offers_relocation: bool = Field(False, description="Whether the job offers relocation assistance")
