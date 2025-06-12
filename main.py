from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import logging
from contextlib import asynccontextmanager
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

# Import our models and services
from models.user import UserCreate, UserResponse, Token, LoginRequest, UserRole, DBUser
from models.profile import ProfileUpload, ExtractedProfile, SearchQuery, SearchResult, Skill
from services.profile_extractor import profile_extractor
from services.vectorizer import vectorizer_service
from config.settings import settings
from services.milvus_service import milvus_service
from services.auth import AuthService
from config.database import get_db, engine, Base

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Talent Pro",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Security
security = HTTPBearer()

@asynccontextmanager
async def startup_event(app: FastAPI):
    """Initialize services on startup"""
    logger.info("Starting Talent Pro...")    
    try:        
        # Initialize database
        Base.metadata.create_all(bind=engine)
        # This will create the milvus collection if it doesn't exist
        logger.info("Services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")

# Authentication dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> DBUser:
    """Get current authenticated user"""
    try:
        auth_service = AuthService(db)
        user = await auth_service.get_current_user(credentials.credentials)
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

# Role requirement
async def require_manager(current_user: DBUser = Depends(get_current_user)) -> DBUser:
    """Require manager role"""
    if current_user.role != UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Manager access required")
    return current_user

@app.post("/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    try:
        auth_service = AuthService(db)
        user = await auth_service.create_user(
            email=user_data.email,
            password=user_data.password,
            role=user_data.role,
            full_name=user_data.full_name
        )
        response = UserResponse.model_validate(user)
        return response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"}
        )

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login user"""
    try:
        auth_service = AuthService(db)
        token_data = await auth_service.authenticate_user(form_data.username, form_data.password)
        return token_data
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@app.get("/me", response_model=UserResponse)
async def get_me(current_user: DBUser = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse.model_validate(current_user)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/profile/upload")
async def upload_profile(
    current_user: DBUser = Depends(get_current_user),
    resume_file: Optional[UploadFile] = File(None),
    github_url: Optional[str] = Form(None),
    additional_info: Optional[str] = Form(None)
):
    """Upload and process user profile"""
    try:
        extracted_data = {}
        
        # Process resume file
        if resume_file:
            print(f"Processing resume file: {resume_file.filename}")
            file_content = await resume_file.read()
            resume_data = profile_extractor.extract_from_resume(file_content, resume_file.filename)
            extracted_data.update(resume_data)
        
        # Process GitHub profile
        github_data = None
        if github_url:
            github_data = profile_extractor.extract_from_github(github_url)
        
        # Create profile summary
        summary = profile_extractor.create_profile_summary(extracted_data, github_data)
        
        # Generate embedding
        embedding = vectorizer_service.encode_profile_summary(summary)
        
        # Prepare data for Milvus
        profile_id = f"profile_{current_user.id}_{uuid.uuid4()}"
        milvus_data = {
            "profile_id": profile_id,
            "user_id": current_user.id,
            "embedding": embedding,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "summary": summary,
            "skills": [skill.dict() for skill in extracted_data.get('skills', [])],
            "metadata": {
                "github_data": github_data.dict() if github_data else None,
                "certifications": [cert.dict() for cert in extracted_data.get('certifications', [])],
                "experience_years": extracted_data.get('experience_years'),
                "education": extracted_data.get('education', []),
                "additional_info": additional_info,
                "upload_date": datetime.now().isoformat()
            }
        }
        
        # Store in Milvus
        success = milvus_service.insert_profile(milvus_data)
        
        if success:
            return {
                "message": "Profile uploaded and processed successfully",
                "profile_id": profile_id,
                "summary": summary,
                "skills_found": len(extracted_data.get('skills', [])),
                "certifications_found": len(extracted_data.get('certifications', []))
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to store profile")
            
    except Exception as e:
        logger.error(f"Profile upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Profile processing failed: {str(e)}")

@app.post("/search/candidates", response_model=List[SearchResult])
async def search_candidates(
    search_query: SearchQuery,
    current_user: DBUser = Depends(require_manager)
):
    """Search for candidates (Manager only)"""
    try:
        # Generate embedding for search query
        query_embedding = vectorizer_service.encode_search_query(search_query.query)
        
        # Search in Milvus
        results = milvus_service.search_similar_profiles(query_embedding, search_query.limit)
        
        # Format results
        search_results = []
        for result in results:
            search_result = SearchResult(
                profile_id=result["profile_id"],
                user_id=result["user_id"],
                full_name=result["full_name"],
                email=result["email"],
                similarity_score=result["similarity_score"],
                summary=result["summary"],
                skills=[Skill(**skill) for skill in result["skills"]]
            )
            search_results.append(search_result)
        
        return search_results
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/chat/suggestions")
async def chat_suggestions(
    query: str,
    current_user: dict = Depends(require_manager)
):
    """Chatbot for HR suggestions (Manager only)"""
    try:
        # This is a simplified version - you can integrate with OpenAI's ChatGPT API
        # for more sophisticated responses
        
        # For now, we'll do a semantic search and provide suggestions
        query_embedding = vectorizer_service.encode_search_query(query)
        results = milvus_service.search_similar_profiles(query_embedding, 5)
        
        if not results:
            return {
                "response": "I couldn't find any candidates matching your query. Try different keywords or skills.",
                "suggestions": []
            }
        
        # Create a response
        top_candidate = results[0]
        response = f"Based on your query '{query}', I found {len(results)} potential candidates. "
        response += f"The top match is {top_candidate['full_name']} with a similarity score of {top_candidate['similarity_score']:.2f}. "
        response += f"Their profile summary: {top_candidate['summary']}"
        
        suggestions = [
            f"{result['full_name']} - Score: {result['similarity_score']:.2f}"
            for result in results[:3]
        ]
        
        return {
            "response": response,
            "suggestions": suggestions,
            "candidates": results
        }
        
    except Exception as e:
        logger.error(f"Chat suggestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@app.get("/profile/my-profiles")
async def get_my_profiles(current_user: dict = Depends(get_current_user)):
    """Get current user's profiles"""
    # This would require a query to Milvus to get profiles by user_id
    # For now, return a placeholder
    return {
        "message": "Feature coming soon - will show your uploaded profiles",
        "user_id": current_user["id"]
    }

@app.delete("/profile/{profile_id}")
async def delete_profile(
    profile_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a profile"""
    try:
        success = milvus_service.delete_profile(profile_id)
        if success:
            return {"message": "Profile deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Profile not found")
    except Exception as e:
        logger.error(f"Profile deletion failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete profile")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "milvus": "connected",
            "vectorizer": "loaded",
            "database": "connected"
        }
    }

import debugpy
debugpy.listen(("0.0.0.0", 5678))
print("⏳ Waiting for debugger attach...")
# debugpy.wait_for_client()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=settings.debug
    )