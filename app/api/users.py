from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.user import UserMeResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserMeResponse)
async def get_current_user_info(current_admin: TokenData = Depends(get_current_admin)):
    """Get current logged-in user information"""
    return {
        "user_id": current_admin.user_id,
        "username": current_admin.username,
        "user_role": current_admin.user_role,  # ✅ Changed from user_role
        "message": "Current authenticated user"
    }


@router.post("/logout")  # ✅ FIX: Remove Depends(get_current_admin)
async def logout():
    """
    Logout endpoint (no authentication required)
    JWT logout is client-side by clearing tokens
    This endpoint is optional and used for audit/logging purposes
    """
    return {
        "message": "Logout successful",
        "note": "Tokens cleared from client storage"
    }