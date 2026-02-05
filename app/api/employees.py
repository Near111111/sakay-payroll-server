from fastapi import APIRouter, Depends
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("/")
async def get_all_employees(current_admin: TokenData = Depends(get_current_admin)):
    """
    Get all employees - Admin only
    Returns list of all employees in the payroll system
    """
    return {
        "message": "List of all employees",
        "admin": current_admin.username
    }


@router.post("/")
async def create_employee(current_admin: TokenData = Depends(get_current_admin)):
    """Create new employee - Admin only"""
    return {
        "message": "Employee created",
        "created_by": current_admin.username
    }