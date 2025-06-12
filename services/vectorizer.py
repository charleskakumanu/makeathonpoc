from sentence_transformers import SentenceTransformer
from typing import List, Union
import logging
import openai
from config.settings import settings

logger = logging.getLogger(__name__)

class VectorizerService:
    def __init__(self):
        self.model = None
        self.use_openai = settings.openai_api_key is not None
        
        if self.use_openai:
            openai.api_key = settings.openai_api_key
            logger.info("Using OpenAI embeddings")
        else:
            # Load local sentence transformer model
            try:
                self.model = SentenceTransformer(settings.embedding_model)
                logger.info(f"Loaded local embedding model: {settings.embedding_model}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
    
    def encode_text(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Convert text to embedding vector(s)"""
        try:
            if self.use_openai:
                return self._encode_with_openai(text)
            else:
                return self._encode_with_local_model(text)
        except Exception as e:
            logger.error(f"Failed to encode text: {e}")
            raise
    
    def _encode_with_openai(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Use OpenAI embeddings"""
        if isinstance(text, str):
            response = openai.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        else:
            response = openai.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return [item.embedding for item in response.data]
    
    def _encode_with_local_model(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Use local sentence transformer model"""
        embeddings = self.model.encode(text)
        
        if isinstance(text, str):
            return embeddings.tolist()
        else:
            return [emb.tolist() for emb in embeddings]
    
    def encode_profile_summary(self, summary: str) -> List[float]:
        """Encode profile summary for storage"""
        return self.encode_text(summary)
    
    def encode_search_query(self, query: str) -> List[float]:
        """Encode search query for similarity search"""
        return self.encode_text(query)

# Global instance
vectorizer_service = VectorizerService()