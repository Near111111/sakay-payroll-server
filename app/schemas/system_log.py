from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SystemLogCreate(BaseModel):
    user_id: int
    activity_type: str  # ADD, EDIT, DELETE
    employee_id: Optional[int] = None
    employee_name_fn: Optional[str] = None
    employee_name_mi: Optional[str] = None
    employee_name_ln: Optional[str] = None
    employee_suffix: Optional[str] = None  # ✅ Added
    payroll_id: Optional[int] = None


class SystemLogResponse(BaseModel):
    activity_id: int
    user_id: int
    activity_type: str
    log_time: datetime
    employee_id: Optional[int] = None
    employee_name_fn: Optional[str] = None
    employee_name_mi: Optional[str] = None
    employee_name_ln: Optional[str] = None
    employee_suffix: Optional[str] = None  # ✅ Added
    payroll_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class SystemLogList(BaseModel):
    logs: list[SystemLogResponse]
    total: int