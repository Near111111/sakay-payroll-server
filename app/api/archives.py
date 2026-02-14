from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_admin
from app.schemas.auth import TokenData
from app.schemas.archive import ArchiveReportCreate, ArchiveReportResponse, ArchiveListResponse
from app.services.archive_service import ArchiveService

router = APIRouter(prefix="/archives", tags=["Archives"])

archive_service = ArchiveService()


@router.post("/", response_model=dict)
async def create_archive(
    archive_data: ArchiveReportCreate,
    current_admin: TokenData = Depends(get_current_admin)
):
    """
    Archive all current payrolls - Admin only
    
    Steps:
    1. Creates archive_report entry
    2. Copies all payrolls with employee data to archive_payrolls
    3. Deletes all payrolls from payrolls table
    """
    try:
        return await archive_service.create_archive(
            archive_date=archive_data.archive_report_date,
            user_id=current_admin.user_id,
            username=current_admin.username
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=ArchiveListResponse)
async def get_all_archives(
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get all archive reports - Admin only"""
    try:
        return await archive_service.get_all_archives()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{archive_report_id}")
async def get_archive_by_id(
    archive_report_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Get specific archive with all payrolls - Admin only"""
    try:
        return await archive_service.get_archive_by_id(archive_report_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{archive_report_id}")
async def delete_archive(
    archive_report_id: int,
    current_admin: TokenData = Depends(get_current_admin)
):
    """Delete archive report and all its payrolls - Admin only"""
    try:
        return await archive_service.delete_archive(archive_report_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))