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
