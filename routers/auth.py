# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from models.user import User
from services.auth import AuthService
from config.settings import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")



@router.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login and get access token"""
    try:
        auth_service = AuthService(db)
        token_data = await auth_service.authenticate_user(
            form_data.username, 
            form_data.password
        )
        return {
            "access_token": token_data["access_token"],
            "token_type": "bearer",
            "expires_in": token_data["expires_in"],
            "user_role": token_data["user_role"]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me")
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Get current authenticated user info"""
    try:
        auth_service = AuthService(db)
        user = await auth_service.get_current_user(token)
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh")
async def refresh_token(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Refresh access token"""
    try:
        auth_service = AuthService(db)
        new_token = await auth_service.refresh_token(token)
        return {
            "access_token": new_token["access_token"],
            "token_type": "bearer",
            "expires_in": new_token["expires_in"]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Logout user (invalidate token)"""
    try:
        auth_service = AuthService(db)
        await auth_service.logout_user(token)
        return {"message": "Logged out successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/change-password")
async def change_password(
    old_password: str,
    new_password: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Change user password"""
    try:
        auth_service = AuthService(db)
        await auth_service.change_password(token, old_password, new_password)
        return {"message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/forgot-password")
async def forgot_password(
    email: str,
    db: Session = Depends(get_db)
):
    """Request password reset"""
    try:
        auth_service = AuthService(db)
        await auth_service.request_password_reset(email)
        return {"message": "Password reset email sent"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/reset-password")
async def reset_password(
    token: str,
    new_password: str,
    db: Session = Depends(get_db)
):
    """Reset password with token"""
    try:
        auth_service = AuthService(db)
        await auth_service.reset_password(token, new_password)
        return {"message": "Password reset successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )