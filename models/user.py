from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship
from models.base import Base

class UserRole(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"

class DBUser(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    role = Column(SQLAlchemyEnum(UserRole))
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    profile = relationship("DBProfile", back_populates="user", uselist=False)
    job_postings = relationship("DBJobPosting", back_populates="poster", lazy="dynamic")

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str