from openai import AsyncOpenAI
from src.config import settings

def prepare_resume_text_for_embedding(structured_data: dict) -> str:
    """
    Convert structured resume data into a single text representation
    optimized for semantic search and similarity matching.
    """
    parts = []
    
    # Contact info
    if contact := structured_data.get("contact"):
        if name := contact.get("name"):
            parts.append(f"Name: {name}")
        if location := contact.get("location"):
            parts.append(f"Location: {location}")
    
    # Summary
    if summary := structured_data.get("summary"):
        parts.append(f"Summary: {summary}")
    
    # Experience (most important for matching)
    if experience := structured_data.get("experience", []):
        parts.append("Experience:")
        for job in experience:
            company = job.get("company", "")
            title = job.get("title", "")
            parts.append(f"{title} at {company}")
            for bullet in job.get("bullets", []):
                parts.append(bullet)
    
    # Skills
    if skills := structured_data.get("skills", []):
        parts.append(f"Skills: {', '.join(skills)}")
    
    # Projects
    if projects := structured_data.get("projects", []):
        parts.append("Projects:")
        for project in projects:
            name = project.get("name", "")
            desc = project.get("description", "")
            techs = project.get("technologies", [])
            parts.append(f"{name}: {desc}")
            if techs:
                parts.append(f"Technologies: {', '.join(techs)}")

    # AI Projects
    if ai_projects := structured_data.get("ai_projects", []):
        parts.append("AI Projects:")
        for project in ai_projects:
            name = project.get("name", "")
            desc = project.get("description", "")
            techs = project.get("technologies", [])
            parts.append(f"{name}: {desc}")
            if techs:
                parts.append(f"Technologies: {', '.join(techs)}")

    # Military Service
    if military := structured_data.get("military_service"):
        parts.append(f"Military Service: {military}")
    
    # Education
    if education := structured_data.get("education", []):
        parts.append("Education:")
        for edu in education:
            school = edu.get("school", "")
            degree = edu.get("degree", "")
            parts.append(f"{degree} from {school}")
    
    # Interests
    if interests := structured_data.get("interests", []):
        parts.append(f"Interests and Certifications: {', '.join(interests)}")
        
    return "\n".join(parts)


class EmbeddingService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "text-embedding-3-small"  # 1536 dimensions
    
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for given text"""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding
    
    @staticmethod
    def prepare_resume_text_for_embedding(structured_data: dict) -> str:
        return prepare_resume_text_for_embedding(structured_data)
