from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PayrollApprovalRequest(BaseModel):
    period_start_date: str
    period_end_date: str
    approver_role: str  # "accounting" or "ceo"


class PayrollApprovalResponse(BaseModel):
    approval_id: int
    period_start_date: str
    period_end_date: str
    approved_by_accounting: Optional[bool] = False
    approved_by_ceo: Optional[bool] = False
    accounting_approved_at: Optional[datetime] = None
    ceo_approved_at: Optional[datetime] = None