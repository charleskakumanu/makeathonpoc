# models/job_posting.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from models.base import Base
from models.user import DBUser

class DBJobPosting(Base):
    __tablename__ = "job_postings"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    required_skills = Column(Text)  # JSON string of skills
    experience_level = Column(String(50))
    department = Column(String(100))
    location = Column(String(255))
    posted_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    poster = relationship("DBUser", back_populates="job_postings")    