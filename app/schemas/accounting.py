from pydantic import BaseModel, model_validator
from typing import Optional, List, Dict
from datetime import datetime


# ─────────────────────────────────────────────
# FILE
# ─────────────────────────────────────────────

class AccountingFileResponse(BaseModel):
    file_id:    int
    file_name:  str
    file_type:  str
    file_url:   str
    file_size:  Optional[int] = None
    created_at: Optional[datetime] = None


# ─────────────────────────────────────────────
# RECORD
# ─────────────────────────────────────────────

AMOUNT_REQUIRED_TYPES = {"expense", "sales", "orders"}


class AccountingRecordCreate(BaseModel):
    title:  str
    type:   str   # expense | sales | orders | other
    notes:  Optional[str]   = None
    amount: Optional[float] = None

    @model_validator(mode="after")
    def check_amount(self):
        if self.type in AMOUNT_REQUIRED_TYPES and self.amount is None:
            raise ValueError(f"'amount' is required for type '{self.type}'")
        return self


class AccountingRecordUpdate(BaseModel):
    title:  Optional[str]   = None
    type:   Optional[str]   = None
    notes:  Optional[str]   = None
    amount: Optional[float] = None


class AccountingRecordResponse(BaseModel):
    record_id:  int
    title:      str
    type:       str
    amount:     Optional[float] = None
    notes:      Optional[str]   = None
    created_by: Optional[int]   = None
    created_at: datetime
    files:      List[AccountingFileResponse] = []


class AccountingListResponse(BaseModel):
    records: List[AccountingRecordResponse]
    total:   int


# ─────────────────────────────────────────────
# MONTHLY SUMMARY
# ─────────────────────────────────────────────

class AccountingMonthlySummary(BaseModel):
    month:         int
    year:          int
    total_expense: float
    total_income:  float
    net:           float
    breakdown:     Dict[str, float]   # e.g. {"expense": 1500, "sales": 3000, "orders": 500}


# ─────────────────────────────────────────────
# ARCHIVE
# ─────────────────────────────────────────────

class AccountingArchivedRecord(BaseModel):
    archive_id:     int
    record_id:      int
    title:          str
    type:           str
    amount:         Optional[float] = None
    notes:          Optional[str]   = None
    created_by:     Optional[int]   = None
    created_at:     datetime
    archived_month: int
    archived_year:  int
    archived_at:    datetime
    files:          List[AccountingFileResponse] = []


class AccountingArchivePeriod(BaseModel):
    year:           int
    month:          int
    total_expense:  float
    total_income:   float
    net:            float
    records:        List[AccountingArchivedRecord]
    total_records:  int


class AccountingArchiveResponse(BaseModel):
    archives:      List[AccountingArchivePeriod]
    total_periods: int


# ─── Add to main.py ───────────────────────────
# from app.api import accounting
# app.include_router(accounting.router)