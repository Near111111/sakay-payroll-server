from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse, EmployeeList
from app.services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["Employees"])

employee_service = EmployeeService()


@router.get("/", response_model=EmployeeList)
async def get_all_employees(
    search: str = Query(None, description="Search by first name, middle initial, or last name"),
    status: str = Query(None, description="Filter by employee status (Regular, Probationary, Contractual, Project-based)"),  # ✅ Added
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get all employees from database - Admin only
    
    Optional query parameters:
    - search: Filter employees by name
    - status: Filter by employee status (Regular, Probationary, Contractual, Project-based)
    
    Examples:
    - /employees/ - Get all employees
    - /employees/?search=juan - Search for employees
    - /employees/?status=Regular - Get only regular employees
    - /employees/?search=maria&status=Regular - Combine filters
    """
    return await employee_service.get_all_employees(search=search, status=status)  # ✅ Pass status


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