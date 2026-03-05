from app.core.supabase_client import get_supabase
from app.services.system_log_service import SystemLogService
from app.schemas.system_log import SystemLogCreate
from fastapi import HTTPException, status, UploadFile
from typing import List, Optional
import uuid
import os


BUCKET = "accounting-files"
ALLOWED_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "text/csv": "csv",
    "application/pdf": "pdf",
    "image/jpeg": "image",
    "image/png": "image",
    "image/jpg": "image",
    "image/webp": "image",
}


class AccountingService:
    def __init__(self):
        self.supabase = get_supabase()
        self.log_service = SystemLogService()

    # ─────────────────────────────────────────────
    # RECORDS
    # ─────────────────────────────────────────────

    async def get_all_records(self):
        try:
            records = self.supabase.table("accounting_records") \
                .select("*") \
                .order("created_at", desc=True) \
                .execute()

            result = []
            for record in records.data:
                files = self.supabase.table("accounting_files") \
                    .select("*") \
                    .eq("record_id", record["record_id"]) \
                    .execute()
                result.append({**record, "files": files.data})

            return {"records": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_record_by_id(self, record_id: int):
        try:
            record = self.supabase.table("accounting_records") \
                .select("*").eq("record_id", record_id).execute()
            if not record.data:
                raise HTTPException(status_code=404, detail="Record not found")

            files = self.supabase.table("accounting_files") \
                .select("*").eq("record_id", record_id).execute()

            return {**record.data[0], "files": files.data}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def create_record(self, title: str, type: str, notes: Optional[str], user_id: int):
        try:
            result = self.supabase.table("accounting_records").insert({
                "title": title,
                "type": type,
                "notes": notes,
                "created_by": user_id,
            }).execute()

            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create record")

            record_id = result.data[0].get('record_id', '')
            try:
                await self.log_service.create_log(SystemLogCreate(
                    user_id=user_id, activity_type="ADD",
                    description=f"[ACCOUNTING] Created record: {title} (type: {type}, ID: {record_id})"
                ))
            except Exception:
                pass

            return {**result.data[0], "files": []}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def update_record(self, record_id: int, title: Optional[str], type: Optional[str], notes: Optional[str], user_id: int = None):
        try:
            existing = self.supabase.table("accounting_records") \
                .select("*").eq("record_id", record_id).execute()
            if not existing.data:
                raise HTTPException(status_code=404, detail="Record not found")

            update_dict = {}
            if title is not None: update_dict["title"] = title
            if type is not None: update_dict["type"] = type
            if notes is not None: update_dict["notes"] = notes

            self.supabase.table("accounting_records") \
                .update(update_dict).eq("record_id", record_id).execute()

            if user_id:
                try:
                    await self.log_service.create_log(SystemLogCreate(
                        user_id=user_id, activity_type="EDIT",
                        description=f"[ACCOUNTING] Updated record ID: {record_id} — {existing.data[0].get('title', '')}"
                    ))
                except Exception:
                    pass

            return await self.get_record_by_id(record_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_record(self, record_id: int, user_id: int = None):
        """Delete record + all its files from storage and DB"""
        try:
            # Get record info for logging
            record = self.supabase.table("accounting_records") \
                .select("*").eq("record_id", record_id).execute()

            # Get files first to delete from storage
            files = self.supabase.table("accounting_files") \
                .select("*").eq("record_id", record_id).execute()

            for file in files.data:
                self._delete_from_storage(file["file_url"])

            record_title = record.data[0].get('title', '') if record.data else ''

            # Delete record (cascades to accounting_files)
            self.supabase.table("accounting_records") \
                .delete().eq("record_id", record_id).execute()

            if user_id:
                try:
                    await self.log_service.create_log(SystemLogCreate(
                        user_id=user_id, activity_type="DELETE",
                        description=f"[ACCOUNTING] Deleted record: {record_title} (ID: {record_id})"
                    ))
                except Exception:
                    pass

            return {"message": f"Record {record_id} deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_all_records(self, user_id: int):
        """Delete ALL records and files"""
        try:
            # Get all files to delete from storage
            files = self.supabase.table("accounting_files").select("*").execute()
            for file in files.data:
                self._delete_from_storage(file["file_url"])

            # Delete all records (cascades to files)
            self.supabase.table("accounting_records").delete().neq("record_id", 0).execute()

            return {"message": "All records deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─────────────────────────────────────────────
    # FILES
    # ─────────────────────────────────────────────

    async def upload_file(self, record_id: int, file: UploadFile, user_id: int = None):
        try:
            # Validate record exists
            record = self.supabase.table("accounting_records") \
                .select("record_id").eq("record_id", record_id).execute()
            if not record.data:
                raise HTTPException(status_code=404, detail="Record not found")

            # Validate file type
            file_type = ALLOWED_TYPES.get(file.content_type)
            if not file_type:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type not allowed: {file.content_type}. Allowed: xlsx, csv, pdf, images"
                )

            # Generate unique filename
            ext = file.filename.split(".")[-1].lower()
            unique_name = f"{record_id}/{uuid.uuid4()}.{ext}"

            # Read file content
            content = await file.read()
            file_size = len(content)

            # Upload to Supabase Storage
            self.supabase.storage.from_(BUCKET).upload(
                path=unique_name,
                file=content,
                file_options={"content-type": file.content_type}
            )

            # Get public/signed URL
            url_response = self.supabase.storage.from_(BUCKET).create_signed_url(
                unique_name, expires_in=60 * 60 * 24 * 365  # 1 year
            )
            file_url = url_response.get("signedURL") or url_response.get("signed_url", "")

            # Save to DB
            db_result = self.supabase.table("accounting_files").insert({
                "record_id": record_id,
                "file_name": file.filename,
                "file_type": file_type,
                "file_url": file_url,
                "file_size": file_size,
            }).execute()

            return db_result.data[0] if db_result.data else {}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_file(self, file_id: int, user_id: int = None):
        try:
            file = self.supabase.table("accounting_files") \
                .select("*").eq("file_id", file_id).execute()
            if not file.data:
                raise HTTPException(status_code=404, detail="File not found")

            self._delete_from_storage(file.data[0]["file_url"])
            self.supabase.table("accounting_files") \
                .delete().eq("file_id", file_id).execute()

            return {"message": f"File {file_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _delete_from_storage(self, file_url: str):
        """Extract path from URL and delete from Supabase Storage"""
        try:
            # Extract path after bucket name in URL
            if BUCKET in file_url:
                path = file_url.split(f"{BUCKET}/")[-1].split("?")[0]
                self.supabase.storage.from_(BUCKET).remove([path])
        except Exception:
            pass  # Don't fail if storage delete fails