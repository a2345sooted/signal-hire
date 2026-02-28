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
    def prepare_resume_text_for_embedding(structured_data: dict) -> str:
        return json.dumps(structured_data, indent=2)
