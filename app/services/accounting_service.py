from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete, cache_delete_pattern
from app.core.storage_client import storage_upload, storage_delete, storage_presigned_url
from app.services.system_log_service import SystemLogService
from app.schemas.system_log import SystemLogCreate
from fastapi import HTTPException, status, UploadFile
from typing import Optional
from datetime import datetime
import uuid

FILE_KEY_PREFIX = "accounting-files"
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

# Types that require an amount value
AMOUNT_REQUIRED_TYPES = {"expense", "sales", "orders"}

RECORDS_LIST_TTL = 300   # 5 minutes
RECORD_TTL = 600         # 10 minutes


# REMOVE the whole function and replace with:
def _enrich_files_with_urls(files: list) -> list:
    """Attach a fresh presigned URL to each file, reconstructing the S3 key from whatever is stored."""
    result = []
    for f in files:
        file_path = f.get("file_path") or f.get("file_url", "")
        try:
            if file_path.startswith("http"):
                # Strip query string to get the bare object path
                clean = file_path.split("?")[0]
                if FILE_KEY_PREFIX in clean:
                    # e.g. https://.../accounting-files/57/uuid.png
                    file_path = FILE_KEY_PREFIX + "/" + clean.split(f"{FILE_KEY_PREFIX}/")[-1]
                else:
                    # Older records stored without prefix — path after bucket name
                    # e.g. https://t3.storageapi.dev/bucket-xxx/57/uuid.png
                    # Extract everything after the bucket segment
                    parts = clean.split("/")
                    # Find the bucket segment (contains "bucket-") and take the rest
                    bucket_idx = next(
                        (i for i, p in enumerate(parts) if "bucket-" in p or "storageapi" in p.lower()),
                        None
                    )
                    if bucket_idx is not None and bucket_idx + 1 < len(parts):
                        file_path = "/".join(parts[bucket_idx + 1:])
                    # else fall through with whatever file_path was
            presigned_url = storage_presigned_url(file_path)
        except Exception:
            presigned_url = file_path
        result.append({**f, "file_url": presigned_url, "file_path": file_path})
    return result


class AccountingService:
    def __init__(self):
        self.log_service = SystemLogService()

    # ─────────────────────────────────────────────
    # AUTO-ARCHIVE (called on every create_record)
    # ─────────────────────────────────────────────

    async def _maybe_archive_previous_month(self, current_user_id: int):
        """
        If there are records whose created_at month != the current month,
        move them (and their files) to the archive tables, then delete from live tables.

        This is called once at the start of create_record so the very first
        write of a new month triggers the archive of the previous month.
        """
        try:
            now = datetime.utcnow()
            current_month = now.month
            current_year = now.year

            # Find records that belong to a past month
            stale = db_fetch_all(
                """
                SELECT record_id, title, type, amount, notes, created_by, created_at
                FROM accounting_records
                WHERE EXTRACT(MONTH FROM created_at) != :month
                   OR EXTRACT(YEAR  FROM created_at) != :year
                """,
                {"month": current_month, "year": current_year}
            )

            if not stale.data:
                return  # nothing to archive

            for rec in stale.data:
                rid = rec["record_id"]
                rec_month = rec["created_at"].month if hasattr(rec["created_at"], "month") else current_month
                rec_year  = rec["created_at"].year  if hasattr(rec["created_at"], "year")  else current_year

                # --- archive the record row ---
                db_execute(
                    """
                    INSERT INTO accounting_records_archive
                        (record_id, title, type, amount, notes, created_by, created_at,
                         archived_month, archived_year)
                    VALUES
                        (:record_id, :title, :type, :amount, :notes, :created_by, :created_at,
                         :archived_month, :archived_year)
                    """,
                    {
                        "record_id":      rid,
                        "title":          rec["title"],
                        "type":           rec["type"],
                        "amount":         rec.get("amount"),
                        "notes":          rec.get("notes"),
                        "created_by":     rec.get("created_by"),
                        "created_at":     rec["created_at"],
                        "archived_month": rec_month,
                        "archived_year":  rec_year,
                    }
                )

                # --- archive associated files ---
                files = db_fetch_all(
                    "SELECT * FROM accounting_files WHERE record_id = :rid",
                    {"rid": rid}
                )
                for f in (files.data or []):
                    db_execute(
                        """
                        INSERT INTO accounting_files_archive
                            (file_id, record_id, file_name, file_type, file_url, file_size,
                             created_at, archived_month, archived_year)
                        VALUES
                            (:file_id, :record_id, :file_name, :file_type, :file_url, :file_size,
                             :created_at, :archived_month, :archived_year)
                        """,
                        {
                            "file_id":        f["file_id"],
                            "record_id":      rid,
                            "file_name":      f.get("file_name"),
                            "file_type":      f.get("file_type"),
                            "file_url":       f.get("file_url"),
                            "file_size":      f.get("file_size"),
                            "created_at":     f.get("created_at"),
                            "archived_month": rec_month,
                            "archived_year":  rec_year,
                        }
                    )

                # --- delete live rows (cascade deletes files if FK set, otherwise manual) ---
                db_execute(
                    "DELETE FROM accounting_files WHERE record_id = :rid",
                    {"rid": rid}
                )
                db_execute(
                    "DELETE FROM accounting_records WHERE record_id = :rid",
                    {"rid": rid}
                )

            cache_delete_pattern("accounting:*")

            try:
                await self.log_service.create_log(SystemLogCreate(
                    user_id=current_user_id,
                    activity_type="ARCHIVE",
                    description=(
                        f"[ACCOUNTING] Auto-archived {len(stale.data)} record(s) "
                        f"from previous month(s)"
                    )
                ))
            except Exception:
                pass

        except Exception:
            # Archive errors must never block record creation
            pass

    # ─────────────────────────────────────────────
    # MONTHLY SUMMARY
    # ─────────────────────────────────────────────

    async def get_monthly_summary(self):
        """
        Returns total expenses and total income (sales + orders) for the current month,
        plus a breakdown per type and a grand net (income - expense).
        """
        try:
            cache_key = "accounting:summary:current_month"
            cached = cache_get(cache_key)
            if cached:
                return cached

            now = datetime.utcnow()

            rows = db_fetch_all(
                """
                SELECT type, COALESCE(SUM(amount), 0) AS total
                FROM accounting_records
                WHERE amount IS NOT NULL
                  AND EXTRACT(MONTH FROM created_at) = :month
                  AND EXTRACT(YEAR  FROM created_at) = :year
                GROUP BY type
                """,
                {"month": now.month, "year": now.year}
            )

            breakdown = {row["type"]: float(row["total"]) for row in (rows.data or [])}

            total_expense = breakdown.get("expense", 0.0)
            total_income  = breakdown.get("sales",   0.0) + breakdown.get("orders", 0.0)
            net           = total_income - total_expense

            response = {
                "month":          now.month,
                "year":           now.year,
                "total_expense":  total_expense,
                "total_income":   total_income,
                "net":            net,
                "breakdown":      breakdown,
            }

            cache_set(cache_key, response, RECORDS_LIST_TTL)
            return response

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ─────────────────────────────────────────────
    # ARCHIVE RETRIEVAL
    # ─────────────────────────────────────────────

    async def get_archive(self, year: Optional[int] = None, month: Optional[int] = None):
        """
        Returns archived records. Optionally filter by year and/or month.
        Also returns per-month summaries.
        """
        try:
            params = {}
            where_clauses = []

            if year is not None:
                where_clauses.append("r.archived_year = :year")
                params["year"] = year
            if month is not None:
                where_clauses.append("r.archived_month = :month")
                params["month"] = month

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            rows = db_fetch_all(
                f"""
                SELECT
                    r.archive_id, r.record_id, r.title, r.type, r.amount,
                    r.notes, r.created_by, r.created_at,
                    r.archived_month, r.archived_year, r.archived_at,
                    f.file_id, f.file_name, f.file_type, f.file_url AS file_path, f.file_size
                FROM accounting_records_archive r
                LEFT JOIN accounting_files_archive f ON f.record_id = r.record_id
                  AND f.archived_month = r.archived_month
                  AND f.archived_year  = r.archived_year
                {where_sql}
                ORDER BY r.archived_year DESC, r.archived_month DESC, r.record_id ASC
                """,
                params
            )

            # Group by archive period → record
            periods: dict = {}
            for row in (rows.data or []):
                period_key = (row["archived_year"], row["archived_month"])
                if period_key not in periods:
                    periods[period_key] = {"records": {}, "year": row["archived_year"], "month": row["archived_month"]}

                rid = row["record_id"]
                if rid not in periods[period_key]["records"]:
                    periods[period_key]["records"][rid] = {
                        "archive_id":     row["archive_id"],
                        "record_id":      row["record_id"],
                        "title":          row["title"],
                        "type":           row["type"],
                        "amount":         float(row["amount"]) if row.get("amount") is not None else None,
                        "notes":          row.get("notes"),
                        "created_by":     row.get("created_by"),
                        "created_at":     row["created_at"],
                        "archived_month": row["archived_month"],
                        "archived_year":  row["archived_year"],
                        "archived_at":    row["archived_at"],
                        "files":          [],
                    }
                if row["file_id"]:
                    periods[period_key]["records"][rid]["files"].append({
                        "file_id":   row["file_id"],
                        "file_name": row["file_name"],
                        "file_type": row["file_type"],
                        "file_path": row["file_path"],
                        "file_size": row["file_size"],
                    })

            # Build output list sorted newest first
            result = []
            for (yr, mo), period in sorted(periods.items(), reverse=True):
                records_list = list(period["records"].values())
                for rec in records_list:
                    rec["files"] = _enrich_files_with_urls(rec["files"])

                # Compute summary for this archived period
                total_expense = sum(r["amount"] or 0 for r in records_list if r["type"] == "expense")
                total_income  = sum(r["amount"] or 0 for r in records_list if r["type"] in ("sales", "orders"))

                result.append({
                    "year":          yr,
                    "month":         mo,
                    "total_expense": total_expense,
                    "total_income":  total_income,
                    "net":           total_income - total_expense,
                    "records":       records_list,
                    "total_records": len(records_list),
                })

            return {"archives": result, "total_periods": len(result)}

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
                    r.record_id, r.title, r.type, r.amount, r.notes, r.created_by, r.created_at,
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
                        "record_id":  row["record_id"],
                        "title":      row["title"],
                        "type":       row["type"],
                        "amount":     float(row["amount"]) if row.get("amount") is not None else None,
                        "notes":      row["notes"],
                        "created_by": row["created_by"],
                        "created_at": row["created_at"],
                        "files":      []
                    }
                if row["file_id"]:
                    records_map[rid]["files"].append({
                        "file_id":   row["file_id"],
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
                    r.record_id, r.title, r.type, r.amount, r.notes, r.created_by, r.created_at,
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
                "record_id":  first["record_id"],
                "title":      first["title"],
                "type":       first["type"],
                "amount":     float(first["amount"]) if first.get("amount") is not None else None,
                "notes":      first["notes"],
                "created_by": first["created_by"],
                "created_at": first["created_at"],
                "files":      []
            }
            for row in rows.data:
                if row["file_id"]:
                    record["files"].append({
                        "file_id":   row["file_id"],
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

    async def create_record(
        self,
        title: str,
        type: str,
        notes: Optional[str],
        user_id: int,
        amount: Optional[float] = None,
    ):
        # Validate: expense / sales / orders must have an amount
        if type in AMOUNT_REQUIRED_TYPES and amount is None:
            raise HTTPException(
                status_code=422,
                detail=f"'amount' is required for type '{type}'"
            )

        # Trigger auto-archive before inserting the new record
        await self._maybe_archive_previous_month(user_id)

        try:
            result = db_execute(
                """
                INSERT INTO accounting_records (title, type, amount, notes, created_by)
                VALUES (:title, :type, :amount, :notes, :created_by)
                RETURNING *
                """,
                {"title": title, "type": type, "amount": amount, "notes": notes, "created_by": user_id}
            )
            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create record")

            cache_delete("accounting:records:all")
            cache_delete("accounting:summary:current_month")

            record_id = result.data[0].get("record_id", "")
            try:
                await self.log_service.create_log(SystemLogCreate(
                    user_id=user_id, activity_type="ADD",
                    description=(
                        f"[ACCOUNTING] Created record: {title} "
                        f"(type: {type}, amount: {amount}, ID: {record_id})"
                    )
                ))
            except Exception:
                pass

            return {**result.data[0], "files": []}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def update_record(
        self,
        record_id: int,
        title: Optional[str],
        type: Optional[str],
        notes: Optional[str],
        amount: Optional[float] = None,
        user_id: int = None,
    ):
        try:
            existing = db_fetch_one(
                "SELECT * FROM accounting_records WHERE record_id = :record_id",
                {"record_id": record_id}
            )
            if not existing.data:
                raise HTTPException(status_code=404, detail="Record not found")

            # Determine the effective type after this update
            effective_type = type if type is not None else existing.data[0].get("type")
            effective_amount = amount if amount is not None else existing.data[0].get("amount")

            if effective_type in AMOUNT_REQUIRED_TYPES and effective_amount is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"'amount' is required for type '{effective_type}'"
                )

            fields = []
            params = {"record_id": record_id}
            if title is not None:
                fields.append("title = :title");   params["title"] = title
            if type is not None:
                fields.append("type = :type");     params["type"] = type
            if notes is not None:
                fields.append("notes = :notes");   params["notes"] = notes
            if amount is not None:
                fields.append("amount = :amount"); params["amount"] = amount

            if fields:
                db_execute(
                    f"UPDATE accounting_records SET {', '.join(fields)} WHERE record_id = :record_id",
                    params
                )

            cache_delete(f"accounting:record:{record_id}")
            cache_delete("accounting:records:all")
            cache_delete("accounting:summary:current_month")

            if user_id:
                try:
                    await self.log_service.create_log(SystemLogCreate(
                        user_id=user_id, activity_type="EDIT",
                        description=(
                            f"[ACCOUNTING] Updated record ID: {record_id} — "
                            f"{existing.data[0].get('title', '')}"
                        )
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

            if not rows.data:
                raise HTTPException(status_code=404, detail="Record not found")

            record_title = rows.data[0].get("title", "")

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
            cache_delete("accounting:summary:current_month")

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
            unique_name = f"{FILE_KEY_PREFIX}/{record_id}/{uuid.uuid4()}.{ext}"
            content = await file.read()
            file_size = len(content)

            storage_upload(unique_name, content, file.content_type)

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
                    "file_url":  unique_name,
                    "file_size": file_size,
                }
            )

            if not db_result.data:
                return {}

            cache_delete(f"accounting:record:{record_id}")
            cache_delete("accounting:records:all")

            row = db_result.data[0]
            presigned_url = storage_presigned_url(unique_name)
            return {**row, "file_url": presigned_url, "file_path": unique_name}

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
                if FILE_KEY_PREFIX in clean:
                    file_path = FILE_KEY_PREFIX + "/" + clean.split(f"{FILE_KEY_PREFIX}/")[-1]
                else:
                    parts = clean.split("/")
                    bucket_idx = next(
                        (i for i, p in enumerate(parts) if "bucket-" in p or "storageapi" in p.lower()),
                        None
                    )
                    if bucket_idx is not None and bucket_idx + 1 < len(parts):
                        file_path = "/".join(parts[bucket_idx + 1:])
            storage_delete(file_path)
        except Exception:
            pass