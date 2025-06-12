from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App settings
    app_name: str = "Talent Pro"
    debug: bool = False  # Default to False for security
    
    # Security
    secret_key: str  # Required from environment
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Milvus settings
    milvus_host: str
    milvus_collection_name: str = "candidate_profiles"  # Using MILVUS_COLLECTION_NAME from .env
    milvus_username: str
    milvus_password: str
    
    # OpenAI settings (for embeddings and chat)
    openai_api_key: Optional[str] = None  # Optional since we can use local models
    
    # GitHub settings
    github_token: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    # Database settings (for user management)
    database_url: str = "sqlite:///./talent.db"
    
    # Embedding model
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

settings = Settings()