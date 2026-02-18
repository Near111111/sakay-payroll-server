from fastapi import APIRouter, HTTPException, Depends, Request
from app.schemas.auth import (
    UserRegister, 
    UserResponse, 
    UserLogin, 
    TokenResponse,
    TokenRefresh,
    TokenData
)
from app.services.auth_service import AuthService
from app.core.dependencies import get_current_admin
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_service = AuthService()


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, user: UserRegister):
    """Register a new ADMIN user"""
    new_user = await auth_service.register_user(user)
    return {
        "user_id": new_user["user_id"],
        "username": new_user["username"],
        "user_role": new_user["user_role"]
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, user: UserLogin):
    """Admin login - Get access token + refresh token"""
    return await auth_service.login_user(user)


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request, token_data: TokenRefresh):
    """Refresh access token using refresh token"""
    return await auth_service.refresh_access_token(token_data)


@router.post("/logout")
@limiter.limit("20/minute")
async def logout(request: Request, current_admin: TokenData = Depends(get_current_admin)):
    """
    Logout current user
    
    Client-side logout (JWT tokens are stateless)
    Frontend should delete tokens from localStorage after calling this.
    """
    return {
        "message": f"User {current_admin.username} logged out successfully",
        "user_id": current_admin.user_id,
        "username": current_admin.username
    }
