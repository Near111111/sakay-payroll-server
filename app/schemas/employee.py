from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime


class EmployeeBase(BaseModel):
    employee_name_fn: str
    employee_name_mi: Optional[str] = None
    employee_name_ln: str
    employee_suffix: Optional[str] = None
    employee_position: Optional[str] = None
    employee_status: Optional[str] = "Regular"  # ✅ NEW - Default to Regular
    basic_pay: Optional[float] = None
    salary_rate: Optional[float] = None
    salary: Optional[float] = None
    sss_deduction: Optional[float] = None
    phic_deduction: Optional[float] = None
    pagibig_deduction: Optional[float] = None


class EmployeeCreate(EmployeeBase):
    @field_validator('employee_name_fn')
    def firstname_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('First name cannot be empty')
        return v
    
    @field_validator('employee_name_ln')
    def lastname_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Last name cannot be empty')
        return v
    
    @field_validator('employee_status')
    def validate_status(cls, v):
        if v is None:
            return "Regular"
        
        # ✅ Dropdown values
        valid_statuses = ["Regular", "Probationary", "Contractual", "Project-based"]
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of: {", ".join(valid_statuses)}')
        return v


class EmployeeUpdate(BaseModel):
    """Schema for updating employee - all fields optional"""
    employee_name_fn: Optional[str] = None
    employee_name_mi: Optional[str] = None
    employee_name_ln: Optional[str] = None
    employee_suffix: Optional[str] = None
    employee_position: Optional[str] = None
    employee_status: Optional[str] = None  # ✅ NEW
    basic_pay: Optional[float] = None
    salary_rate: Optional[float] = None
    salary: Optional[float] = None
    sss_deduction: Optional[float] = None
    phic_deduction: Optional[float] = None
    pagibig_deduction: Optional[float] = None
    
    @field_validator('employee_status')
    def validate_status(cls, v):
        if v is None:
            return v
        
        valid_statuses = ["Regular", "Probationary", "Contractual", "Project-based"]
        if v not in valid_statuses:
            raise ValueError(f'Status must be one of: {", ".join(valid_statuses)}')
        return v


class EmployeeResponse(EmployeeBase):
    employee_id: int
    created_at: datetime
    created_by: Optional[int] = None
    
    class Config:
        from_attributes = True


class EmployeeList(BaseModel):
    employees: list[EmployeeResponse]
    total: int
    search: Optional[str] = None
    status_filter: Optional[str] = None