# routers/manager.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import json
from datetime import datetime, timedelta

from models.user import User
from models.profile import Profile
from models.job_posting import JobPosting
from services.auth import AuthService
from services.vectorizer import VectorizerService
from services.milvus_service import MilvusService
from config.settings import get_db

router = APIRouter(prefix="/manager", tags=["manager"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


async def get_current_manager(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Dependency to get current authenticated manager"""
    auth_service = AuthService(db)
    user = await auth_service.get_current_user(token)
    if user.role != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Manager role required"
        )
    return user


@router.get("/employees")
async def get_all_employees(
    page: int = 1,
    per_page: int = 20,
    search: Optional[str] = None,
    skill_filter: Optional[str] = None,
    current_user: User = Depends(get_current_manager),
    db: Session = Depends(get_db)
):
    """Get all employees with pagination and filtering"""
    try:
        query = db.query(User, Profile).outerjoin(
            Profile, User.id == Profile.user_id
        ).filter(User.role == "employee")
        
        # Apply search filter
        if search:
            query = query.filter(
                Profile.full_name.ilike(f"%{search}%") |
                User.email.ilike(f"%{search}%")
            )
        
        # Apply skill filter
        if skill_filter:
            query = query.filter(Profile.skills.ilike(f"%{skill_filter}%"))
        
        # Pagination
        offset = (page - 1) * per_page
        employees = query.offset(offset).limit(per_page).all()
        total = query.count()
        
        employee_list = []
        for user, profile in employees:
            employee_data = {
                "id": user.id,
                "email": user.email,
                "created_at": user.created_at,
                "profile": None
            }
            
            if profile:
                employee_data["profile"] = {
                    "full_name": profile.full_name,
                    "skills": json.loads(profile.skills) if profile.skills else [],
                    "experience": profile.experience,
                    "education": profile.education,
                    "certifications": json.loads(profile.certifications) if profile.certifications else [],
                    "github_url": profile.github_url,
                    "linkedin_url": profile.linkedin_url,
                    "updated_at": profile.updated_at
                }
            
            employee_list.append(employee_data)
        
        return {
            "employees": employee_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching employees: {str(e)}"
        )


@router.get("/employee/{employee_id}")
async def get_employee_detail(
    employee_id: int,
    current_user: User = Depends(get_current_manager),
    db: Session = Depends(get_db)
):
    """Get detailed employee information"""
    try:
        employee = db.query(User).filter(
            User.id == employee_id,
            User.role == "employee"
        ).first()
        
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found"
            )
        
        profile = db.query(Profile).filter(Profile.user_id == employee_id).first()
        
        employee_data = {
            "id": employee.id,
            "email": employee.email,
            "created_at": employee.created_at,
            "profile": None
        }
        
        if profile:
            employee_data["profile"] = {
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
        
        return employee_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching employee details: {str(e)}"
        )


@router.post("/job-posting")
async def create_job_posting(
    title: str,
    description: str,
    required_skills: List[str],
    experience_level: str,
    department: Optional[str] = None,
    location: Optional[str] = None,
    current_user: User = Depends(get_current_manager),
    db: Session = Depends(get_db)
):
    """Create a new job posting and store in vector database"""
    try:
        # Create job posting data
        job_data = {
            "title": title,
            "description": description,
            "required_skills": required_skills,
            "experience_level": experience_level,
            "department": department,
            "location": location,
            "posted_by": current_user.id,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Vectorize job requirements
        vectorizer = VectorizerService()
        job_vector = vectorizer.vectorize_job_requirements(required_skills, description)
        
        # Store in Milvus
        milvus_service = MilvusService()
        job_id = await milvus_service.insert_job_vector(job_data, job_vector)
        
        return {
            "message": "Job posting created successfully",
            "job_id": job_id,
            "job_data": job_data
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating job posting: {str(e)}"
        )


@router.get("/job-postings")
async def get_job_postings(
    page: int = 1,
    per_page: int = 10,
    current_user: User = Depends(get_current_manager)
):
    """Get all job postings"""
    try:
        milvus_service = MilvusService()
        job_postings = await milvus_service.get_job_postings(page, per_page)
        
        return {
            "job_postings": job_postings,
            "pagination": {
                "page": page,
                "per_page": per_page
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching job postings: {str(e)}"
        )


@router.post("/find-candidates")
async def find_candidates_for_job(
    job_requirements: Dict[str, Any],
    limit: int = 20,
    current_user: User = Depends(get_current_manager)
):
    """Find matching candidates for job requirements"""
    try:
        # Extract required skills and other criteria
        required_skills = job_requirements.get("required_skills", [])
        job_description = job_requirements.get("description", "")
        experience_level = job_requirements.get("experience_level", "")
        
        if not required_skills:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Required skills must be provided"
            )
        
        # Find matching candidates using vector similarity
        milvus_service = MilvusService()
        vectorizer = VectorizerService()
        
        job_vector = vectorizer.vectorize_job_requirements(required_skills, job_description)
        candidates = await milvus_service.find_candidate_matches(job_vector, limit)
        
        return {
            "candidates": candidates,
            "job_requirements": job_requirements,
            "total_matches": len(candidates)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding candidates: {str(e)}"
        )


@router.get("/analytics/skills")
async def get_skills_analytics(
    current_user: User = Depends(get_current_manager),
    db: Session = Depends(get_db)
):
    """Get analytics on employee skills distribution"""
    try:
        profiles = db.query(Profile).filter(Profile.skills.isnot(None)).all()
        
        skill_count = {}
        total_employees = len(profiles)
        
        for profile in profiles:
            if profile.skills:
                skills = json.loads(profile.skills)
                for skill in skills:
                    skill_lower = skill.lower()
                    skill_count[skill_lower] = skill_count.get(skill_lower, 0) + 1
        
        # Sort skills by frequency
        sorted_skills = sorted(skill_count.items(), key=lambda x: x[1], reverse=True)
        
        # Calculate percentages
        skills_analytics = []
        for skill, count in sorted_skills[:20]:  # Top 20 skills
            skills_analytics.append({
                "skill": skill.title(),
                "count": count,
                "percentage": round((count / total_employees) * 100, 2)
            })
        
        return {
            "total_employees": total_employees,
            "total_unique_skills": len(skill_count),
            "top_skills": skills_analytics
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating skills analytics: {str(e)}"
        )


@router.get("/analytics/departments")
async def get_department_analytics(
    current_user: User = Depends(get_current_manager),
    db: Session = Depends(get_db)
):
    """Get analytics on employee distribution by departments (based on skills)"""
    try:
        profiles = db.query(Profile).filter(Profile.skills.isnot(None)).all()
        
        # Define skill-to-department mapping
        department_mapping = {
            "engineering": ["python", "java", "javascript", "react", "node.js", "sql", "docker", "kubernetes"],
            "data_science": ["python", "r", "machine learning", "tensorflow", "pandas", "numpy", "sql"],
            "design": ["figma", "sketch", "photoshop", "ui/ux", "adobe", "design"],
            "marketing": ["marketing", "seo", "content", "social media", "analytics"],
            "operations": ["project management", "operations", "process", "lean", "agile"]
        }
        
        department_counts = {dept: 0 for dept in department_mapping}
        department_employees = {dept: [] for dept in department_mapping}
        
        for profile in profiles:
            if not profile.skills:
                continue
                
            skills = json.loads(profile.skills)
            employee_departments = set()
            
            # Map employee to departments based on their skills
            for skill in skills:
                skill_lower = skill.lower()
                for dept, dept_skills in department_mapping.items():
                    if any(dept_skill in skill_lower for dept_skill in dept_skills):
                        employee_departments.add(dept)
                        department_employees[dept].append({
                            "user_id": profile.user_id,
                            "skill": skill
                        })
            
            # Increment department counters
            for dept in employee_departments:
                department_counts[dept] += 1
        
        total_mapped = sum(department_counts.values())
        
        # Calculate percentages and prepare response
        department_analytics = []
        for dept, count in department_counts.items():
            department_analytics.append({
                "department": dept.replace("_", " ").title(),
                "count": count,
                "percentage": round((count / total_mapped * 100 if total_mapped > 0 else 0), 2),
                "top_skills": _get_top_skills_in_department(department_employees[dept])
            })
        
        return {
            "total_employees_mapped": total_mapped,
            "departments": sorted(department_analytics, key=lambda x: x["count"], reverse=True)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating department analytics: {str(e)}"
        )


def _get_top_skills_in_department(employees: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    """Helper function to get top skills in a department"""
    skill_count = {}
    for employee in employees:
        skill = employee["skill"]
        skill_count[skill] = skill_count.get(skill, 0) + 1
    
    # Sort skills by frequency and return top N
    sorted_skills = sorted(skill_count.items(), key=lambda x: x[1], reverse=True)
    return [{"skill": skill, "count": count} for skill, count in sorted_skills[:limit]]


@router.get("/analytics/trends")
async def get_hiring_trends(
    current_user: User = Depends(get_current_manager),
    db: Session = Depends(get_db)
):
    """Get hiring trends and skills demand analysis"""
    try:
        # Get all job postings from last 6 months
        six_months_ago = datetime.utcnow() - timedelta(days=180)
        job_postings = db.query(JobPosting).filter(JobPosting.created_at >= six_months_ago).all()
        
        # Analyze required skills frequency
        skill_demand = {}
        total_postings = len(job_postings)
        
        for posting in job_postings:
            required_skills = json.loads(posting.required_skills)
            for skill in required_skills:
                skill_lower = skill.lower()
                skill_demand[skill_lower] = skill_demand.get(skill_lower, 0) + 1
        
        # Calculate demand trends
        trends = []
        for skill, count in sorted(skill_demand.items(), key=lambda x: x[1], reverse=True)[:15]:
            trends.append({
                "skill": skill.title(),
                "demand_count": count,
                "demand_percentage": round((count / total_postings * 100 if total_postings > 0 else 0), 2)
            })
        
        return {
            "total_job_postings": total_postings,
            "period": "Last 6 months",
            "top_demanded_skills": trends,
            "analysis_date": datetime.utcnow()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating hiring trends: {str(e)}"
        )


@router.post("/export-report")
async def export_analytics_report(
    report_type: str,
    date_range: Optional[str] = None,
    current_user: User = Depends(get_current_manager)
):
    """Export analytics report in specified format"""
    try:
        # Validate report type
        valid_report_types = ["skills", "departments", "hiring_trends"]
        if report_type not in valid_report_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid report type. Must be one of: {', '.join(valid_report_types)}"
            )
        
        # Generate report data based on type
        report_data = await _generate_report_data(report_type, date_range)
        
        # Generate unique report filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_report_{timestamp}.xlsx"
        
        # Create Excel report
        report_path = await _create_excel_report(report_data, report_type, filename)
        
        return {
            "message": "Report generated successfully",
            "report_type": report_type,
            "filename": filename,
            "download_url": f"/static/reports/{filename}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating report: {str(e)}"
        )


async def _generate_report_data(report_type: str, date_range: Optional[str]) -> Dict[str, Any]:
    """Helper function to generate report data based on type"""
    if report_type == "skills":
        return await get_skills_analytics()
    elif report_type == "departments":
        return await get_department_analytics()
    elif report_type == "hiring_trends":
        return await get_hiring_trends()
    else:
        raise ValueError(f"Unsupported report type: {report_type}")


async def _create_excel_report(data: Dict[str, Any], report_type: str, filename: str) -> str:
    """Helper function to create Excel report"""
    try:
        import pandas as pd
        from pathlib import Path
        
        reports_dir = Path("static/reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = reports_dir / filename
        
        # Convert data to DataFrame based on report type
        if report_type == "skills":
            df = pd.DataFrame(data["top_skills"])
        elif report_type == "departments":
            df = pd.DataFrame(data["departments"])
        elif report_type == "hiring_trends":
            df = pd.DataFrame(data["top_demanded_skills"])
        
        # Save to Excel
        df.to_excel(file_path, index=False)
        return str(file_path)
    except Exception as e:
        raise ValueError(f"Failed to create Excel report: {str(e)}")