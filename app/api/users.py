from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_admin, get_current_super_admin
from app.schemas.auth import TokenData
from app.schemas.user import UserMeResponse
from app.schemas.user_management import UserListResponse, ToggleUserStatusResponse
from app.services.user_management_service import UserManagementService

router = APIRouter(prefix="/users", tags=["Users"])

user_management_service = UserManagementService()


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

@router.get("/all", response_model=UserListResponse)
async def get_all_users(current_admin: TokenData = Depends(get_current_super_admin)):
    """
    [Super Admin only] Get all registered users with their active/disabled status.
    """
    users = user_management_service.get_all_users()
    return {"users": users, "total": len(users)}


@router.patch("/{user_id}/toggle-status", response_model=ToggleUserStatusResponse)
async def toggle_user_status(
    user_id: int,
    current_admin: TokenData = Depends(get_current_super_admin)
):
    """
    [Super Admin only] Enable or disable a user account.
    Disabled users cannot log in but their data is preserved.
    """
    return user_management_service.toggle_user_status(
        target_user_id=user_id,
        requesting_user_id=current_admin.user_id,
        requesting_user_role=current_admin.user_role
    )