from fastapi import APIRouter, Depends, Query, HTTPException
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.payroll import PayrollCreate, PayrollUpdate, PayrollResponse, PayrollList
from app.services.payroll_service import PayrollService

router = APIRouter(prefix="/payrolls", tags=["Payrolls"])

payroll_service = PayrollService()


@router.get("/", response_model=PayrollList)
async def get_all_payrolls(
    employee_id: int = Query(None, description="Filter by employee ID"),
    pay_status: str = Query(None, description="Filter by payment status (Pending, Paid, Cancelled)"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get all payroll records - Admin only
    
    Optional query parameters:
    - employee_id: Filter payrolls by employee
    - pay_status: Filter by payment status
    
    Examples:
    - /payrolls/ - Get all payrolls
    - /payrolls/?employee_id=5 - Get payrolls for employee 5
    - /payrolls/?pay_status=Pending - Get only pending payrolls
    - /payrolls/?employee_id=5&pay_status=Paid - Combine filters
    """
    try:
        return await payroll_service.get_all_payrolls(employee_id=employee_id, pay_status=pay_status)
    except Exception as e:
        print(f"Error getting payrolls: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get payrolls: {str(e)}")


@router.get("/{payroll_id}", response_model=PayrollResponse)
async def get_payroll(
    payroll_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get single payroll record by ID - Admin only"""
    try:
        return await payroll_service.get_payroll_by_id(payroll_id)
    except Exception as e:
        print(f"Error getting payroll: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Payroll with ID {payroll_id} not found")


@router.post("/", response_model=PayrollResponse, status_code=201)
async def create_payroll(
    payroll: PayrollCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Create new payroll record - Admin only
    
    pay_status options:
    - Pending (default)
    - Paid
    - Cancelled
    
    Automatically logs ADD action to system_logs
    """
    try:
        return await payroll_service.create_payroll(payroll, current_admin.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error creating payroll: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create payroll: {str(e)}")


@router.put("/{payroll_id}", response_model=PayrollResponse)
async def update_payroll(
    payroll_id: int,
    payroll_data: PayrollUpdate,
    current_admin: TokenData = Depends(get_current_admin)
):
    try:
        # Convert to dict, excluding fields that weren't sent
        update_dict = payroll_data.model_dump(exclude_unset=True)
        return await payroll_service.update_payroll(payroll_id, update_dict, current_admin.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"Error updating payroll: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update payroll: {str(e)}")


@router.delete("/{payroll_id}")
async def delete_payroll(
    payroll_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Delete payroll record - Admin only
    
    Automatically logs DELETE action to system_logs
    """
    try:
        return await payroll_service.delete_payroll(payroll_id, current_admin.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"Error deleting payroll: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete payroll: {str(e)}")