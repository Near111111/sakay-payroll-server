from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import date, datetime


class PayrollBase(BaseModel):
    employee_id: int
    days_worked: Optional[float] = None
    ot_hours: Optional[float] = None
    no_of_absents: Optional[int] = None
    hours_worked: Optional[float] = None  # ✅ NEW: User input
    tardiness_per_minute: Optional[int] = None
    tardiness_deduction: Optional[float] = None
    absent_deduction: Optional[float] = None  # ✅ NEW: Auto-calculated
    period_start_date: Optional[date] = None
    period_end_date: Optional[date] = None
    other_deductions: Optional[float] = None
    total_deduction: Optional[float] = None
    gross_pay: Optional[float] = None
    net_pay: Optional[float] = None
    working_days: Optional[int] = None
    salary_rate: Optional[float] = None
    salary: Optional[float] = None
    pay_status: Optional[str] = "Pending"


class PayrollCreate(PayrollBase):
    @field_validator('employee_id')
    def validate_employee_id(cls, v):
        if v <= 0:
            raise ValueError('Employee ID must be positive')
        return v
    
    @field_validator('pay_status')
    def validate_pay_status(cls, v):
        if v is None:
            return "Pending"
        
        valid_statuses = ["Pending", "Paid", "Cancelled"]
        if v not in valid_statuses:
            raise ValueError(f'Pay status must be one of: {", ".join(valid_statuses)}')
        return v


class PayrollUpdate(BaseModel):
    """Schema for updating payroll - all fields optional"""
    employee_id: Optional[int] = None
    days_worked: Optional[float] = None
    ot_hours: Optional[float] = None
    no_of_absents: Optional[int] = None
    hours_worked: Optional[float] = None  # ✅ NEW
    tardiness_per_minute: Optional[int] = None
    tardiness_deduction: Optional[float] = None
    absent_deduction: Optional[float] = None  # ✅ NEW
    period_start_date: Optional[date] = None
    period_end_date: Optional[date] = None
    other_deductions: Optional[float] = None
    total_deduction: Optional[float] = None
    gross_pay: Optional[float] = None
    net_pay: Optional[float] = None
    working_days: Optional[int] = None
    salary_rate: Optional[float] = None
    salary: Optional[float] = None
    pay_status: Optional[str] = None
    
    @field_validator('pay_status')
    def validate_pay_status(cls, v):
        if v is None:
            return v
        
        valid_statuses = ["Pending", "Paid", "Cancelled"]
        if v not in valid_statuses:
            raise ValueError(f'Pay status must be one of: {", ".join(valid_statuses)}')
        return v


class PayrollResponse(PayrollBase):
    payroll_id: int
    made_by: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class PayrollList(BaseModel):
    payrolls: list[PayrollResponse]
    total: int
    employee_id_filter: Optional[int] = None
    pay_status_filter: Optional[str] = None