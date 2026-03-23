from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete, cache_delete_pattern
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

RECORDS_LIST_TTL = 300   # 5 minutes
RECORD_TTL = 600         # 10 minutes


def _enrich_files_with_urls(files: list) -> list:
    """Build public URLs for each file."""
    result = []
    for f in files:
        file_path = f.get("file_path") or f.get("file_url", "")
        try:
            if file_path.startswith("http"):
                clean = file_path.split("?")[0]
                if BUCKET in clean:
                    file_path = clean.split(f"{BUCKET}/")[-1]
            public_url = minio_get_public_url(BUCKET, file_path)
        except Exception:
            public_url = file_path
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
            cache_key = "accounting:records:all"
            cached = cache_get(cache_key)
            if cached:
                return cached

            rows = db_fetch_all(
                """
                SELECT
                    r.record_id, r.title, r.type, r.notes, r.created_by, r.created_at,
                    f.file_id, f.file_name, f.file_type, f.file_url AS file_path, f.file_size
                FROM accounting_records r
                LEFT JOIN accounting_files f ON f.record_id = r.record_id
                ORDER BY r.created_at DESC, f.file_id ASC
                """
            )

            records_map = {}
            for row in rows.data:
                rid = row["record_id"]
                if rid not in records_map:
                    records_map[rid] = {
                        "record_id": row["record_id"],
                        "title": row["title"],
                        "type": row["type"],
                        "notes": row["notes"],
                        "created_by": row["created_by"],
                        "created_at": row["created_at"],
                        "files": []
                    }
                if row["file_id"]:
                    records_map[rid]["files"].append({
                        "file_id": row["file_id"],
                        "file_name": row["file_name"],
                        "file_type": row["file_type"],
                        "file_path": row["file_path"],
                        "file_size": row["file_size"],
                    })

            result = []
            for record in records_map.values():
                record["files"] = _enrich_files_with_urls(record["files"])
                result.append(record)

            response = {"records": result, "total": len(result)}
            cache_set(cache_key, response, RECORDS_LIST_TTL)
            return response

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_record_by_id(self, record_id: int):
        try:
            cache_key = f"accounting:record:{record_id}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            rows = db_fetch_all(
                """
                SELECT
                    r.record_id, r.title, r.type, r.notes, r.created_by, r.created_at,
                    f.file_id, f.file_name, f.file_type, f.file_url AS file_path, f.file_size
                FROM accounting_records r
                LEFT JOIN accounting_files f ON f.record_id = r.record_id
                WHERE r.record_id = :record_id
                ORDER BY f.file_id ASC
                """,
                {"record_id": record_id}
            )

            if not rows.data:
                raise HTTPException(status_code=404, detail="Record not found")

            first = rows.data[0]
            record = {
                "record_id": first["record_id"],
                "title": first["title"],
                "type": first["type"],
                "notes": first["notes"],
                "created_by": first["created_by"],
                "created_at": first["created_at"],
                "files": []
            }
            for row in rows.data:
                if row["file_id"]:
                    record["files"].append({
                        "file_id": row["file_id"],
                        "file_name": row["file_name"],
                        "file_type": row["file_type"],
                        "file_path": row["file_path"],
                        "file_size": row["file_size"],
                    })

            record["files"] = _enrich_files_with_urls(record["files"])
            cache_set(cache_key, record, RECORD_TTL)
            return record

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

            cache_delete("accounting:records:all")

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

            cache_delete(f"accounting:record:{record_id}")
            cache_delete("accounting:records:all")

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
            rows = db_fetch_all(
                """
                SELECT r.title, f.file_url
                FROM accounting_records r
                LEFT JOIN accounting_files f ON f.record_id = r.record_id
                WHERE r.record_id = :record_id
                """,
                {"record_id": record_id}
            )

            # ✅ FIX 1: Return 404 if record doesn't exist
            if not rows.data:
                raise HTTPException(status_code=404, detail="Record not found")

            record_title = rows.data[0].get("title", "")

            # ✅ FIX 2: Use file_url only — no file_path column in accounting_files
            for row in rows.data:
                file_path = row.get("file_url", "")
                if file_path:
                    self._delete_from_storage(file_path)

            db_execute(
                "DELETE FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )

            cache_delete(f"accounting:record:{record_id}")
            cache_delete("accounting:records:all")

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
            files = db_fetch_all("SELECT file_path, file_url FROM accounting_files")
            for file in files.data:
                self._delete_from_storage(file.get("file_path") or file.get("file_url", ""))

            db_execute("DELETE FROM accounting_records WHERE record_id > 0")

            cache_delete_pattern("accounting:*")

            try:
                await self.log_service.create_log(SystemLogCreate(
                    user_id=user_id, activity_type="DELETE",
                    description="[ACCOUNTING] Deleted ALL records and files"
                ))
            except Exception:
                pass

            return {"message": "All records deleted successfully"}

        except HTTPException:
            raise
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

            minio_upload(BUCKET, unique_name, content, file.content_type)

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
                    "file_url": unique_name,
                    "file_size": file_size,
                }
            )

            if not db_result.data:
                return {}

            cache_delete(f"accounting:record:{record_id}")
            cache_delete("accounting:records:all")

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

            file_data = file.data[0]
            self._delete_from_storage(file_data.get("file_path") or file_data.get("file_url", ""))

            db_execute(
                "DELETE FROM accounting_files WHERE file_id = :file_id",
                {"file_id": file_id}
            )

            record_id = file_data.get("record_id")
            if record_id:
                cache_delete(f"accounting:record:{record_id}")
            cache_delete("accounting:records:all")

            return {"message": f"File {file_id} deleted"}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _delete_from_storage(self, file_path: str):
        try:
            if not file_path:
                return
            if file_path.startswith("http"):
                clean = file_path.split("?")[0]
                if BUCKET in clean:
                    file_path = clean.split(f"{BUCKET}/")[-1]
            minio_delete(BUCKET, file_path)
        except Exception:
            pass