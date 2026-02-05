from fastapi import APIRouter, HTTPException
from app.schemas.auth import (
    UserRegister, 
    UserResponse, 
    UserLogin, 
    TokenResponse,
    TokenRefresh
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_service = AuthService()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user: UserRegister):
    """
    Register a new ADMIN user
    - **username**: unique admin username
    - **user_password**: password (minimum 8 characters, will be hashed with Argon2)
    
    Note: Only admin users can access this system
    """
    new_user = await auth_service.register_user(user)
    return {
        "user_id": new_user["user_id"],
        "username": new_user["username"],
        "user_role": new_user["user_role"]
    }


@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin):
    """
    Admin login - Get access token + refresh token
    - **username**: admin username
    - **user_password**: admin password
    
    Returns:
    - **access_token**: Short-lived JWT (30 minutes)
    - **refresh_token**: Long-lived JWT (7 days)
    """
    return await auth_service.login_user(user)


@router.post("/refresh")
async def refresh_token(token_data: TokenRefresh):
    """
    Refresh access token using refresh token
    - **refresh_token**: Your refresh token from login
    
    Returns new access token
    """
    return await auth_service.refresh_access_token(token_data)