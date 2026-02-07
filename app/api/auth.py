from fastapi import APIRouter, HTTPException, Depends
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

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_service = AuthService()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user: UserRegister):
    """Register a new ADMIN user"""
    new_user = await auth_service.register_user(user)
    return {
        "user_id": new_user["user_id"],
        "username": new_user["username"],
        "user_role": new_user["user_role"]
    }


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin):
    """Admin login - Get access token + refresh token"""
    return await auth_service.login_user(user)


@router.post("/refresh")
async def refresh_token(token_data: TokenRefresh):
    """Refresh access token using refresh token"""
    return await auth_service.refresh_access_token(token_data)


@router.post("/logout")
async def logout(current_admin: TokenData = Depends(get_current_admin)):
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