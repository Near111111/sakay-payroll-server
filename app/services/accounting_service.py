from app.core.db_client import db_fetch_all, db_fetch_one, db_execute
from app.core.minio_client import minio_upload, minio_delete, minio_get_public_url
from app.services.system_log_service import SystemLogService
from app.schemas.system_log import SystemLogCreate
from fastapi import HTTPException, status, UploadFile
from typing import Optional
import uuid


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





def _enrich_files_with_urls(files: list) -> list:
    """Build public URLs for each file."""
    result = []
    for f in files:
        file_path = f.get("file_path") or f.get("file_url", "")
        try:
            # If file_path is already a full URL (old data), extract the path
            if file_path.startswith("http"):
                clean = file_path.split("?")[0]
                if BUCKET in clean:
                    file_path = clean.split(f"{BUCKET}/")[-1]

            public_url = minio_get_public_url(BUCKET, file_path)
        except Exception:
            public_url = file_path  # fallback

        result.append({**f, "file_url": public_url, "file_path": file_path})
    return result


class AccountingService:
    def __init__(self):
        self.log_service = SystemLogService()

    # ─────────────────────────────────────────────
    # RECORDS
    # ─────────────────────────────────────────────

    async def get_all_records(self):
        try:
            records = db_fetch_all(
                "SELECT * FROM accounting_records ORDER BY created_at DESC"
            )
            result = []
            for record in records.data:
                files = db_fetch_all(
                    "SELECT * FROM accounting_files WHERE record_id = :record_id",
                    {"record_id": record["record_id"]}
                )
                result.append({**record, "files": _enrich_files_with_urls(files.data)})
            return {"records": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_record_by_id(self, record_id: int):
        try:
            record = db_fetch_one(
                "SELECT * FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )
            if not record.data:
                raise HTTPException(status_code=404, detail="Record not found")

            files = db_fetch_all(
                "SELECT * FROM accounting_files WHERE record_id = :record_id",
                {"record_id": record_id}
            )
            return {**record.data[0], "files": _enrich_files_with_urls(files.data)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def create_record(self, title: str, type: str, notes: Optional[str], user_id: int):
        try:
            result = db_execute(
                """
                INSERT INTO accounting_records (title, type, notes, created_by)
                VALUES (:title, :type, :notes, :created_by)
                RETURNING *
                """,
                {"title": title, "type": type, "notes": notes, "created_by": user_id}
            )
            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create record")

            record_id = result.data[0].get("record_id", "")
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
            existing = db_fetch_one(
                "SELECT * FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )
            if not existing.data:
                raise HTTPException(status_code=404, detail="Record not found")

            fields = []
            params = {"record_id": record_id}
            if title is not None:
                fields.append("title = :title")
                params["title"] = title
            if type is not None:
                fields.append("type = :type")
                params["type"] = type
            if notes is not None:
                fields.append("notes = :notes")
                params["notes"] = notes

            if fields:
                db_execute(
                    f"UPDATE accounting_records SET {', '.join(fields)} WHERE record_id = :record_id",
                    params
                )

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
        try:
            record = db_fetch_one(
                "SELECT * FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )
            files = db_fetch_all(
                "SELECT * FROM accounting_files WHERE record_id = :record_id",
                {"record_id": record_id}
            )

            for file in files.data:
                self._delete_from_storage(file.get("file_path") or file.get("file_url", ""))

            record_title = record.data[0].get("title", "") if record.data else ""

            db_execute(
                "DELETE FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )

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
        try:
            files = db_fetch_all("SELECT * FROM accounting_files")
            for file in files.data:
                self._delete_from_storage(file.get("file_path") or file.get("file_url", ""))

            db_execute("DELETE FROM accounting_records WHERE record_id > 0")
            return {"message": "All records deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─────────────────────────────────────────────
    # FILES
    # ─────────────────────────────────────────────

    async def upload_file(self, record_id: int, file: UploadFile, user_id: int = None):
        try:
            record = db_fetch_one(
                "SELECT record_id FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )
            if not record.data:
                raise HTTPException(status_code=404, detail="Record not found")

            file_type = ALLOWED_TYPES.get(file.content_type)
            if not file_type:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type not allowed: {file.content_type}. Allowed: xlsx, csv, pdf, images"
                )

            ext = file.filename.split(".")[-1].lower()
            unique_name = f"{record_id}/{uuid.uuid4()}.{ext}"
            content = await file.read()
            file_size = len(content)

            # Upload to MinIO
            minio_upload(BUCKET, unique_name, content, file.content_type)

            # Save the object PATH (not presigned URL) — fresh URLs generated on each GET
            db_result = db_execute(
                """
                INSERT INTO accounting_files (record_id, file_name, file_type, file_url, file_size)
                VALUES (:record_id, :file_name, :file_type, :file_url, :file_size)
                RETURNING *
                """,
                {
                    "record_id": record_id,
                    "file_name": file.filename,
                    "file_type": file_type,
                    "file_url": unique_name,   # store path, not presigned URL
                    "file_size": file_size,
                }
            )

            if not db_result.data:
                return {}

            # Return with public URL
            row = db_result.data[0]
            public_url = minio_get_public_url(BUCKET, unique_name)
            return {**row, "file_url": public_url, "file_path": unique_name}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_file(self, file_id: int, user_id: int = None):
        try:
            file = db_fetch_one(
                "SELECT * FROM accounting_files WHERE file_id = :file_id",
                {"file_id": file_id}
            )
            if not file.data:
                raise HTTPException(status_code=404, detail="File not found")

            self._delete_from_storage(file.data[0].get("file_path") or file.data[0].get("file_url", ""))
            db_execute(
                "DELETE FROM accounting_files WHERE file_id = :file_id",
                {"file_id": file_id}
            )
            return {"message": f"File {file_id} deleted"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _delete_from_storage(self, file_path: str):
        """Delete object from MinIO. Accepts either a path or a full URL."""
        try:
            if not file_path:
                return
            # If it's a full URL, extract just the path
            if file_path.startswith("http"):
                clean = file_path.split("?")[0]
                if BUCKET in clean:
                    file_path = clean.split(f"{BUCKET}/")[-1]
            minio_delete(BUCKET, file_path)
        except Exception:
            pass