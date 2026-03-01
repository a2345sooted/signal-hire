from typing import List

from pydantic import BaseModel, Field


class MatchGapAnalysisSchema(BaseModel):
    major_hits: List[str] = Field(..., description="Strong signals: Exact experience match, rare skills, exceeding requirements, domain expertise.")
    minor_hits: List[str] = Field(..., description="Positive signals: Adjacent skills, learning trajectory, soft skills, cultural fit.")
    major_gaps: List[str] = Field(..., description="Critical dealbreakers: Missing core tech, required certifications, degree (if mandatory), or minimum years of experience.")
    minor_gaps: List[str] = Field(..., description="Addressable weaknesses: Missing preferred skills, lacks familiarity with specific tools (but has similar), or slightly below experience threshold.")

class ScoreBreakdown(BaseModel):
    skills_match: int = Field(0, description="Score for skills match (max 30)")
    experience_relevance: int = Field(0, description="Score for experience relevance (max 25)")
    seniority: int = Field(0, description="Score for seniority / years of experience (max 15)")
    education_certs: int = Field(0, description="Score for education & certifications (max 10)")
    keyword_coverage: int = Field(0, description="Score for keyword / ATS coverage (max 10)")
    accomplishments: int = Field(0, description="Score for accomplishments vs. responsibilities (max 5)")
    formatting_clarity: int = Field(0, description="Score for formatting & clarity (max 5)")

class DeterministicScoringInput(BaseModel):
    skills_match_score: int = Field(0, description="25–30: Nearly all + most preferred; 15–24: Most + some preferred; 5–14: Partial; 0–4: Minimal.")
    experience_relevance_score: int = Field(0, description="20–25: Direct; 12–19: Adjacent/Transferable; 5–11: Some overlap; 0–4: Unrelated.")
    seniority_score: int = Field(0, description="12–15: Meets/Exceeds; 8–11: Within 1–2 yrs; 4–7: Noticeably under/over; 0–3: Major mismatch.")
    education_certs_score: int = Field(0, description="8–10: Match + Certs; 5–7: Degree present, minor mismatch; 2–4: Unrelated field but experience compensates; 0–1: No degree where required.")
    keyword_coverage_score: int = Field(0, description="8–10: High overlap; 5–7: Moderate; 2–4: Low; 0–1: Almost no matching.")
    accomplishments_score: int = Field(0, description="4–5: Quantified achievements; 2–3: Mix; 0–1: Purely duty-based.")
    formatting_clarity_score: int = Field(0, description="4–5: Clean structure; 2–3: Minor issues; 0–1: Heavy formatting/graphics.")

class ScoringSchema(BaseModel):
    score: int = Field(..., description="Overall match score from 0 to 100")
    breakdown: ScoreBreakdown = Field(..., description="Categorical breakdown of the score")

class AnalysisResultSchema(BaseModel):
    score: int = Field(..., description="Overall match score from 0 to 100")
    # Separate hits/gaps are deprecated in favor of being included in the markdown message.
    # Keeping them here for backward compatibility if needed, but they should be empty in new records.
    major_hits: List[str] = Field(default_factory=list, description="DEPRECATED: Now in message")
    minor_hits: List[str] = Field(default_factory=list, description="DEPRECATED: Now in message")
    major_gaps: List[str] = Field(default_factory=list, description="DEPRECATED: Now in message")
    minor_gaps: List[str] = Field(default_factory=list, description="DEPRECATED: Now in message")
    message: str = Field("", description="Markdown analysis summary containing strengths and gaps")
    # For backward compatibility or internal use if needed
    matches: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
