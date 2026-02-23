from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class AccountingFileResponse(BaseModel):
    file_id: int
    file_name: str
    file_type: str
    file_url: str
    file_size: Optional[int] = None
    created_at: datetime


class AccountingRecordCreate(BaseModel):
    title: str
    type: str  # expense, income, invoice, other
    notes: Optional[str] = None


class AccountingRecordUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    notes: Optional[str] = None


class AccountingRecordResponse(BaseModel):
    record_id: int
    title: str
    type: str
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    files: List[AccountingFileResponse] = []


class AccountingListResponse(BaseModel):
    records: List[AccountingRecordResponse]
    total: int


# ─── Add to main.py ───
# from app.api import accounting
# app.include_router(accounting.router)