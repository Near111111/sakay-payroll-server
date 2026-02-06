from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.employee import EmployeeCreate, EmployeeResponse, EmployeeList
from app.services.employee_service import EmployeeService

router = APIRouter(prefix="/employees", tags=["Employees"])

employee_service = EmployeeService()


@router.get("/", response_model=EmployeeList)
async def get_all_employees(current_admin: TokenData = Depends(get_current_admin)):
    """
    Get all employees from database - Admin only
    """
    return await employee_service.get_all_employees()


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get single employee by ID - Admin only
    """
    return await employee_service.get_employee_by_id(employee_id)


@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Create new employee - Admin only
    """
    return await employee_service.create_employee(employee, current_admin.user_id)


@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    employee_data: dict,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Update employee - Admin only
    """
    return await employee_service.update_employee(employee_id, employee_data)


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Delete employee - Admin only
    """
    return await employee_service.delete_employee(employee_id)