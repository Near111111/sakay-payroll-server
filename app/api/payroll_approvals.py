from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.payroll_approval import PayrollApprovalRequest
from app.services.payroll_approval_service import PayrollApprovalService

router = APIRouter(prefix="/payroll-approvals", tags=["Payroll Approvals"])

approval_service = PayrollApprovalService()


@router.get("/")
async def get_approval(
    period_start: str = Query(..., description="Period start date (YYYY-MM-DD)"),
    period_end: str = Query(..., description="Period end date (YYYY-MM-DD)"),
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get approval status for a specific payroll period"""
    try:
        return await approval_service.get_approval(period_start, period_end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/approve", response_model=dict)
async def approve_payroll(
    approval: PayrollApprovalRequest,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Approve a payroll period by accounting or CEO"""
    try:
        return await approval_service.approve(
            period_start=approval.period_start_date,
            period_end=approval.period_end_date,
            approver_role=approval.approver_role,
            username=current_admin.username
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/unapprove", response_model=dict)
async def unapprove_payroll(
    approval: PayrollApprovalRequest,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Remove approval for a payroll period by accounting or CEO"""
    try:
        return await approval_service.unapprove(
            period_start=approval.period_start_date,
            period_end=approval.period_end_date,
            approver_role=approval.approver_role,
            username=current_admin.username
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))