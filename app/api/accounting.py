from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.services.accounting_service import AccountingService
from typing import Optional, List

router = APIRouter(prefix="/accounting", tags=["Accounting"])

accounting_service = AccountingService()


# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────

@router.get("/summary")
async def get_monthly_summary(
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Get total expenses vs income (sales + orders) for the current month.
    Returns a net figure and a per-type breakdown.
    """
    return await accounting_service.get_monthly_summary()


# ─────────────────────────────────────────────
# ARCHIVE
# ─────────────────────────────────────────────

@router.get("/archive")
async def get_archive(
    year:  Optional[int] = None,
    month: Optional[int] = None,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Retrieve archived records (previous months).
    Optionally filter by ?year=2025&month=3
    Returns records grouped by period with per-period summaries.
    """
    return await accounting_service.get_archive(year=year, month=month)


# ─────────────────────────────────────────────
# RECORDS
# ─────────────────────────────────────────────

@router.get("/records")
async def get_all_records(
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get all accounting records (current month) with their files"""
    return await accounting_service.get_all_records()


@router.get("/records/{record_id}")
async def get_record(
    record_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get single record with files"""
    return await accounting_service.get_record_by_id(record_id)


@router.post("/records", status_code=201)
async def create_record(
    title:  str            = Form(...),
    type:   str            = Form(...),
    notes:  Optional[str]  = Form(None),
    amount: Optional[float] = Form(None),
    files:  List[UploadFile] = File(default=[]),
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Create a new accounting record.
    - `amount` is REQUIRED for type: expense | sales | orders
    - `amount` is OPTIONAL (ignored) for type: other
    Accepts multipart/form-data so files can be uploaded at the same time.
    On the first create of a new month, previous-month records are auto-archived.
    """
    record = await accounting_service.create_record(
        title=title,
        type=type,
        notes=notes,
        amount=amount,
        user_id=current_admin.user_id
    )

    if files:
        for file in files:
            if file.filename:
                await accounting_service.upload_file(record["record_id"], file)

    return await accounting_service.get_record_by_id(record["record_id"])


@router.put("/records/{record_id}")
async def update_record(
    record_id: int,
    title:  Optional[str]   = Form(None),
    type:   Optional[str]   = Form(None),
    notes:  Optional[str]   = Form(None),
    amount: Optional[float] = Form(None),
    current_admin: TokenData = Depends(get_current_admin)
):
    """Update record title, type, notes, or amount"""
    return await accounting_service.update_record(
        record_id, title, type, notes, amount, current_admin.user_id
    )


@router.delete("/records")
async def delete_all_records(
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete ALL current-month records and files"""
    return await accounting_service.delete_all_records(current_admin.user_id)


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete a specific record and all its files"""
    return await accounting_service.delete_record(record_id, current_admin.user_id)


# ─────────────────────────────────────────────
# FILES
# ─────────────────────────────────────────────

@router.post("/records/{record_id}/files", status_code=201)
async def upload_file(
    record_id: int,
    file: UploadFile = File(...),
    current_admin: TokenData = Depends(get_current_admin)
):
    """Upload a single file to an existing record"""
    return await accounting_service.upload_file(record_id, file, current_admin.user_id)


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete a specific file"""
    return await accounting_service.delete_file(file_id, current_admin.user_id)