# routers/employee.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from models.user import User
from models.profile import Profile
from services.auth import AuthService
from services.profile_extractor import ProfileExtractor
from services.vectorizer import VectorizerService
from services.milvus_service import MilvusService
from config.settings import get_db

router = APIRouter(prefix="/employee", tags=["employee"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


async def get_current_employee(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Dependency to get current authenticated employee"""
    auth_service = AuthService(db)
    user = await auth_service.get_current_user(token)
    if user.role != "employee":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Employee role required"
        )
    return user


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Get employee profile"""
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        return {"message": "Profile not found", "profile": None}
    
    return {
        "profile": {
            "id": profile.id,
            "full_name": profile.full_name,
            "skills": json.loads(profile.skills) if profile.skills else [],
            "experience": profile.experience,
            "education": profile.education,
            "certifications": json.loads(profile.certifications) if profile.certifications else [],
            "github_url": profile.github_url,
            "linkedin_url": profile.linkedin_url,
            "resume_url": profile.resume_url,
            "updated_at": profile.updated_at
        }
    }


@router.post("/profile")
async def create_update_profile(
    full_name: str,
    experience: Optional[str] = None,
    education: Optional[str] = None,
    github_url: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    skills: Optional[List[str]] = None,
    certifications: Optional[List[str]] = None,
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Create or update employee profile"""
    try:
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        
        if not profile:
            profile = Profile(user_id=current_user.id)
            db.add(profile)
        
        profile.full_name = full_name
        profile.experience = experience
        profile.education = education
        profile.github_url = github_url
        profile.linkedin_url = linkedin_url
        profile.skills = json.dumps(skills) if skills else None
        profile.certifications = json.dumps(certifications) if certifications else None
        
        db.commit()
        db.refresh(profile)
        
        return {
            "message": "Profile updated successfully",
            "profile_id": profile.id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating profile: {str(e)}"
        )


@router.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Upload and process resume"""
    try:
        if not file.filename.lower().endswith(('.pdf', '.doc', '.docx')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF, DOC, and DOCX files are allowed"
            )
        
        # Extract profile data from resume
        extractor = ProfileExtractor()
        profile_data = await extractor.extract_from_resume(file)
        
        # Update or create profile
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        if not profile:
            profile = Profile(user_id=current_user.id)
            db.add(profile)
        
        # Update profile with extracted data
        if profile_data.get('skills'):
            profile.skills = json.dumps(profile_data['skills'])
        if profile_data.get('experience'):
            profile.experience = profile_data['experience']
        if profile_data.get('education'):
            profile.education = profile_data['education']
        if profile_data.get('certifications'):
            profile.certifications = json.dumps(profile_data['certifications'])
        
        profile.resume_url = f"uploads/resumes/{current_user.id}_{file.filename}"
        
        db.commit()
        db.refresh(profile)
        
        # Generate and store vectors
        vectorizer = VectorizerService()
        milvus_service = MilvusService()
        
        skill_vector = vectorizer.vectorize_skills(profile_data.get('skills', []))
        await milvus_service.insert_profile_vector(current_user.id, skill_vector)
        
        return {
            "message": "Resume uploaded and processed successfully",
            "extracted_data": profile_data,
            "profile_id": profile.id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing resume: {str(e)}"
        )


@router.post("/sync-github")
async def sync_github_profile(
    github_username: str,
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Sync GitHub profile and extract skills"""
    try:
        extractor = ProfileExtractor()
        github_data = await extractor.extract_from_github(github_username)
        
        # Update profile
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        if not profile:
            profile = Profile(user_id=current_user.id)
            db.add(profile)
        
        profile.github_url = f"https://github.com/{github_username}"
        
        # Merge existing skills with GitHub skills
        existing_skills = json.loads(profile.skills) if profile.skills else []
        github_skills = github_data.get('skills', [])
        merged_skills = list(set(existing_skills + github_skills))
        profile.skills = json.dumps(merged_skills)
        
        db.commit()
        db.refresh(profile)
        
        # Update vectors
        vectorizer = VectorizerService()
        milvus_service = MilvusService()
        
        skill_vector = vectorizer.vectorize_skills(merged_skills)
        await milvus_service.update_profile_vector(current_user.id, skill_vector)
        
        return {
            "message": "GitHub profile synced successfully",
            "github_data": github_data,
            "merged_skills": merged_skills
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error syncing GitHub profile: {str(e)}"
        )


@router.get("/job-matches")
async def get_job_matches(
    limit: int = 10,
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Get job recommendations based on employee profile"""
    try:
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        if not profile or not profile.skills:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile not found or no skills available"
            )
        
        milvus_service = MilvusService()
        job_matches = await milvus_service.find_job_matches(current_user.id, limit)
        
        return {
            "matches": job_matches,
            "total_matches": len(job_matches)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding job matches: {str(e)}"
        )


@router.get("/skills")
async def get_skill_suggestions(
    query: Optional[str] = None,
    current_user: User = Depends(get_current_employee)
):
    """Get skill suggestions for autocomplete"""
    try:
        vectorizer = VectorizerService()
        suggestions = await vectorizer.get_skill_suggestions(query)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting skill suggestions: {str(e)}"
        )


@router.delete("/profile")
async def delete_profile(
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Delete employee profile"""
    try:
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        
        # Remove from vector database
        milvus_service = MilvusService()
        await milvus_service.delete_profile_vector(current_user.id)
        
        # Delete profile
        db.delete(profile)
        db.commit()
        
        return {"message": "Profile deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting profile: {str(e)}"
        )


@router.get("/dashboard")
async def get_dashboard_data(
    current_user: User = Depends(get_current_employee),
    db: Session = Depends(get_db)
):
    """Get employee dashboard data"""
    try:
        profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
        
        dashboard_data = {
            "profile_completion": 0,
            "total_skills": 0,
            "job_matches_count": 0,
            "recent_activity": []
        }
        
        if profile:
            # Calculate profile completion
            fields = [profile.full_name, profile.experience, profile.education, 
                     profile.skills, profile.github_url, profile.resume_url]
            completed_fields = sum(1 for field in fields if field)
            dashboard_data["profile_completion"] = (completed_fields / len(fields)) * 100
            
            # Count skills
            if profile.skills:
                skills = json.loads(profile.skills)
                dashboard_data["total_skills"] = len(skills)
            
            # Get job matches count
            try:
                milvus_service = MilvusService()
                matches = await milvus_service.find_job_matches(current_user.id, 5)
                dashboard_data["job_matches_count"] = len(matches)
            except:
                pass  # Milvus might not be available
        
        return dashboard_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting dashboard data: {str(e)}"
        )