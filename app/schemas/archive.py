from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

class ArchiveReportCreate(BaseModel):
    archive_report_date: str

class ArchiveApprovalRequest(BaseModel):
    approver_role: str  # "accounting" or "ceo"

class ArchiveReportResponse(BaseModel):
    archive_report_id: int
    archive_report_date: str
    created_at: datetime
    total_payrolls_archived: Optional[int] = 0
    approved_by_accounting: Optional[bool] = False
    approved_by_ceo: Optional[bool] = False
    accounting_approved_at: Optional[datetime] = None
    ceo_approved_at: Optional[datetime] = None

class ArchivePayrollResponse(BaseModel):
    archive_payroll_id: int
    archive_report_id: int
    employee_id: int
    employee_name_fn: str
    employee_name_mi: Optional[str]
    employee_name_ln: str
    employee_suffix: Optional[str]
    employee_position: str
    days_worked: float
    ot_hours: float
    no_of_absents: int
    hours_worked: float
    tardiness_per_minute: int
    tardiness_deduction: float
    absent_deduction: float
    period_start_date: date
    period_end_date: date
    other_deductions: float
    deduction_reason: Optional[str]
    total_deduction: float
    gross_pay: float
    net_pay: float
    working_days: int
    salary_rate: float
    salary: float
    pay_status: str
    made_by: str
    created_at: datetime
    sss_deduction: float
    phic_deduction: float
    pagibig_deduction: float
    basic_pay: float

class ArchiveReportWithPayrolls(BaseModel):
    archive_report: ArchiveReportResponse
    payrolls: List[ArchivePayrollResponse]

class ArchiveListResponse(BaseModel):
    archives: List[ArchiveReportResponse]
    total: int