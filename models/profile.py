from enum import Enum
from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from models.base import Base

class SkillLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class Skill(BaseModel):
    name: str
    level: SkillLevel
    years_of_experience: Optional[int] = None

class Certification(BaseModel):
    name: str
    issuer: str
    issue_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None

class GitHubProfile(BaseModel):
    username: str
    repositories: List[str]
    languages: Dict[str, int]  # language -> lines of code
    contributions: int
    followers: int
    following: int

class ProfileUpload(BaseModel):
    resume_file: Optional[str] = None  # base64 encoded file
    github_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    additional_info: Optional[str] = None

class ExtractedProfile(BaseModel):
    user_id: int
    full_name: str
    email: str
    skills: List[Skill]
    certifications: List[Certification]
    experience_years: Optional[int] = None
    education: List[str]
    github_data: Optional[GitHubProfile] = None
    summary: str  # Human readable summary
    
class ProfileVector(BaseModel):
    profile_id: str
    user_id: int
    embedding: List[float]
    metadata: Dict[str, Any]
    
class SearchQuery(BaseModel):
    query: str
    limit: int = 10
    
class SearchResult(BaseModel):
    profile_id: str
    user_id: int
    full_name: str
    email: str
    similarity_score: float
    summary: str
    skills: List[Skill]

class DBProfile(Base):
    __tablename__ = "profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    full_name = Column(String(200))
    email = Column(String(200))
    summary = Column(Text)
    skills = Column(JSON)  # List[Skill]
    certifications = Column(JSON)  # List[Certification]
    experience_years = Column(Integer, nullable=True)
    education = Column(JSON)  # List[str]
    github_data = Column(JSON, nullable=True)  # Optional[GitHubProfile]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("DBUser", back_populates="profile")    