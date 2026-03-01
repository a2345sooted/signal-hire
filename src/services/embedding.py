import json
import tiktoken
from openai import AsyncOpenAI
from src.config import settings

class EmbeddingService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "text-embedding-3-small"  # 1536 dimensions
        try:
            self.encoding = tiktoken.encoding_for_model(self.model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def chunk_text(self, text: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
        """
        Split text into chunks of maximum max_tokens with given overlap.
        """
        if not text:
            return []
            
        tokens = self.encoding.encode(text)
        chunks = []
        
        for i in range(0, len(tokens), max_tokens - overlap):
            chunk_tokens = tokens[i : i + max_tokens]
            chunks.append(self.encoding.decode(chunk_tokens))
            if i + max_tokens >= len(tokens):
                break
                
        return chunks

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for given text"""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding
    
    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for multiple texts"""
        if not texts:
            return []
            
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        # OpenAI returns them in order, but let's be safe and map them
        return [item.embedding for item in response.data]

    @staticmethod
    def prepare_resume_text_for_embedding(structured_data: dict, candidate_data: dict = None, notes: list = None) -> str:
        data = {
            "resume": structured_data
        }
        if candidate_data:
            # Only include relevant metadata
            data["candidate_metadata"] = {
                "name": candidate_data.get("name"),
                "location": candidate_data.get("location"),
                "citizenship": candidate_data.get("citizenship"),
                "engagement_types": candidate_data.get("engagement_types"),
                "work_preference": candidate_data.get("work_preference"),
                "open_to_relocation": candidate_data.get("open_to_relocation")
            }
        if notes:
            data["candidate_notes"] = [n.get("content") for n in notes if n.get("content")]
            
        return json.dumps(data, indent=2)

    @staticmethod
    def prepare_job_text_for_embedding(structured_data: dict, job_data: dict = None, notes: list = None) -> str:
        data = {
            "job": structured_data or {}
        }
        if job_data:
            data["job_metadata"] = {
                "title": job_data.get("title"),
                "location": job_data.get("location"),
                "work_arrangement": job_data.get("work_arrangement"),
                "hybrid_days_per_week": job_data.get("hybrid_days_per_week"),
                "pay_range_min": job_data.get("pay_range_min"),
                "pay_range_max": job_data.get("pay_range_max"),
                "pay_type": job_data.get("pay_type"),
                "employment_type": job_data.get("employment_type"),
                "offers_relocation": job_data.get("offers_relocation")
            }
        if notes:
            data["job_notes"] = [n.get("content") for n in notes if n.get("content")]
            
        return json.dumps(data, indent=2)
