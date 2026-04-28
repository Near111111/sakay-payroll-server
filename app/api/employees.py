from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from app.core.dependencies import get_current_admin
from app.core.storage_client import storage_upload, storage_presigned_url
from app.core.db_client import db_execute, cache_delete, cache_delete_pattern
from app.schemas.auth import TokenData
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeeList
from app.services.employee_service import EmployeeService
import uuid

router = APIRouter(prefix="/employees", tags=["Employees"])

employee_service = EmployeeService()

PHOTO_KEY_PREFIX = "employee-photos"
ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp"
}


@router.get("/", response_model=EmployeeList)
async def get_all_employees(
    search: str = Query(None, description="Search by first name, middle initial, or last name"),
    status: str = Query(None, description="Filter by employee status (Regular, Probationary, Contractual, Project-based)"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get all employees from database - Admin only

    Optional query parameters:
    - search: Filter employees by name
    - status: Filter by employee status (Regular, Probationary, Contractual, Project-based)
    """
    return await employee_service.get_all_employees(search=search, status=status)


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get single employee by ID - Admin only"""
    return await employee_service.get_employee_by_id(employee_id)


@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Create new employee - Admin only

    employee_status options (for dropdown):
    - Regular (default)
    - Probationary
    - Contractual
    - Project-based

    Automatically logs ADD action to system_logs
    """
    return await employee_service.create_employee(employee, current_admin.user_id)


@router.post("/{employee_id}/photo")
async def upload_employee_photo(
    employee_id: int,
    file: UploadFile = File(...),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Upload or replace employee photo - Admin only

    - Uploads image to S3
    - Generates presigned URL and saves directly to image_metadata in DB
    - Replaces any existing photo
    - Allowed types: jpg, jpeg, png, webp
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: jpg, jpeg, png, webp"
        )

    # Check employee exists
    await employee_service.get_employee_by_id(employee_id)

    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    s3_key = f"{PHOTO_KEY_PREFIX}/{employee_id}/{uuid.uuid4()}.{ext}"

    content = await file.read()
    storage_upload(s3_key, content, file.content_type)

    # Generate presigned URL and save directly to image_metadata
    presigned_url = storage_presigned_url(s3_key)

    db_execute(
        "UPDATE employees SET image_metadata = :url WHERE employee_id = :employee_id",
        {"url": presigned_url, "employee_id": employee_id}
    )

    # Invalidate caches
    cache_delete(f"employees:{employee_id}")
    cache_delete_pattern("employees:list:*")

    return {"url": presigned_url, "employee_id": employee_id}


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    employee_data: EmployeeUpdate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Update employee - Admin only

    All fields are optional - only provide fields you want to update
    Can update employee_status using dropdown values

    Automatically logs EDIT action to system_logs
    """
    update_dict = employee_data.model_dump(exclude_unset=True)
    return await employee_service.update_employee(employee_id, update_dict, current_admin.user_id)


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Delete employee - Admin only

    Note: Cannot delete employee if they have payroll records
    Automatically logs DELETE action to system_logs
    """
    return await employee_service.delete_employee(employee_id, current_admin.user_id)