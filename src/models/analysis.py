from typing import List

from pydantic import BaseModel, Field


class MatchGapAnalysisSchema(BaseModel):
    major_hits: List[str] = Field(..., description="Strong signals: Exact experience match, rare skills, exceeding requirements, domain expertise.")
    minor_hits: List[str] = Field(..., description="Positive signals: Adjacent skills, learning trajectory, soft skills, cultural fit.")
    major_gaps: List[str] = Field(..., description="Critical dealbreakers: Missing core tech, required certifications, degree (if mandatory), or minimum years of experience.")
    minor_gaps: List[str] = Field(..., description="Addressable weaknesses: Missing preferred skills, lacks familiarity with specific tools (but has similar), or slightly below experience threshold.")

class ScoreBreakdown(BaseModel):
    critical_requirements: int = Field(0, description="Score for must-have skills/experience (max 40)")
    important_requirements: int = Field(0, description="Score for should-have skills/experience (max 25)")
    nice_to_have: int = Field(0, description="Score for preferred qualifications (max 10)")
    experience_level: int = Field(0, description="Score for years & relevance of experience (max 15)")
    presentation: int = Field(0, description="Score for resume quality & relevance (max 10)")

class DeterministicScoringInput(BaseModel):
    critical_hits_count: int = Field(0, description="Number of major hits against critical JD requirements.")
    major_gap_penalties: List[int] = Field(default_factory=list, description="List of deductions (10-15) for each major gap.")
    specific_penalties: List[int] = Field(default_factory=list, description="List of specific penalties: 20 (missing cert), 15 (missing core skill), 12 (missing years threshold).")
    
    important_hits_count: int = Field(0, description="Number of minor hits.")
    partial_skill_hits_count: int = Field(0, description="Number of related/transferable skills (50% value).")
    learning_skill_hits_count: int = Field(0, description="Number of skills being learned (20% value).")
    minor_gap_penalties: List[int] = Field(default_factory=list, description="List of deductions (5-8) for each minor gap.")
    has_85_percent_important: bool = Field(False, description="Whether they have 85%+ of important requirements (+2 bonus).")
    
    nice_to_have_hits_count: int = Field(0, description="Number of nice-to-have hits (1 pt each).")
    
    experience_years_match_score: int = Field(0, description="10-12 (Meets), 5-7 (Slightly under), 0-2 (Significantly under), 8-10 (Overqualified).")
    experience_multiplier: float = Field(1.0, description="Multiplier: 1.0 (Directly relevant), 0.6 (Adjacent), 0.4 (Transferable).")
    experience_bonus_penalty: int = Field(0, description="Upward trajectory (+1), Job hopping (-3), Career pivot (0).")
    
    presentation_quality_score: int = Field(0, description="Well-organized (4), Acceptable (2), Poor (0).")
    tailoring_score: int = Field(0, description="Clearly tailored (4), Generic (1), Spray-and-pray (0).")
    presentation_bonus_penalty: int = Field(0, description="Quantified achievements (+1), Typos (-3), Unexplained gaps > 1yr (-3).")

class ScoringSchema(BaseModel):
    score: int = Field(..., description="Overall match score from 0 to 100")
    breakdown: ScoreBreakdown = Field(..., description="Categorical breakdown of the score")
    reasoning: str = Field(..., description="Detailed explanation of the mathematical calculation and reasoning")

class AnalysisResultSchema(BaseModel):
    score: int = Field(..., description="Overall match score from 0 to 100")
    major_hits: List[str] = Field(..., description="Strong signals")
    minor_hits: List[str] = Field(..., description="Positive signals")
    major_gaps: List[str] = Field(..., description="Critical dealbreakers")
    minor_gaps: List[str] = Field(..., description="Addressable weaknesses")
    # For backward compatibility or internal use if needed, we can keep old fields as optional or remove them
    matches: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
