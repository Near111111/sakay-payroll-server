from fastapi import APIRouter, Depends, Query
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.system_log import SystemLogCreate, SystemLogResponse, SystemLogList
from app.services.system_log_service import SystemLogService

router = APIRouter(prefix="/system-logs", tags=["System Logs"])

log_service = SystemLogService()


@router.post("/", response_model=SystemLogResponse, status_code=201)
async def create_log(
    log: SystemLogCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Create a new system log entry
    
    Activity types:
    - ADD: When creating a new employee
    - EDIT: When updating an employee
    - DELETE: When deleting an employee
    """
    return await log_service.create_log(log)


@router.get("/", response_model=SystemLogList)
async def get_all_logs(
    activity_type: str = Query(None, description="Filter by activity type (ADD, EDIT, DELETE)"),
    user_id: int = Query(None, description="Filter by user ID"),
    employee_id: int = Query(None, description="Filter by employee ID"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get all system logs with optional filters
    
    Filters:
    - activity_type: ADD, EDIT, DELETE
    - user_id: Filter logs by user who performed the action
    - employee_id: Filter logs by affected employee
    """
    return await log_service.get_all_logs(activity_type, user_id, employee_id)


@router.get("/user/{user_id}", response_model=SystemLogList)
async def get_user_activity(
    user_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get all activities performed by a specific user"""
    return await log_service.get_user_activity(user_id)


@router.get("/employee/{employee_id}", response_model=SystemLogList)
async def get_employee_history(
    employee_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get all activities related to a specific employee"""
    return await log_service.get_employee_history(employee_id)