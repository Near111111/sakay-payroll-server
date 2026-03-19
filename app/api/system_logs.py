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
    """Create a new system log entry"""
    return await log_service.create_log(log)


@router.get("/")
async def get_all_logs(
    activity_type: str = Query(None, description="Filter by activity type (ADD, EDIT, DELETE)"),
    user_id: int = Query(None, description="Filter by user ID"),
    employee_id: int = Query(None, description="Filter by employee ID"),
    # ✅ NEW: Pagination params
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    limit: int = Query(5, ge=1, le=100, description="Items per page (default 5, max 100)"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get system logs with optional filters and pagination.

    Examples:
    - /system-logs/              → page 1, 5 items
    - /system-logs/?page=2       → page 2, 5 items
    - /system-logs/?page=1&limit=10  → page 1, 10 items
    - /system-logs/?activity_type=ADD&page=1 → filtered + paginated

    Returns:
    - logs: list of logs for this page
    - total: total number of matching logs
    - page: current page
    - limit: items per page
    - total_pages: total number of pages
    - has_next: whether there is a next page
    - has_prev: whether there is a previous page
    """
    return await log_service.get_all_logs(
        activity_type=activity_type,
        user_id=user_id,
        employee_id=employee_id,
        page=page,
        limit=limit,
    )


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