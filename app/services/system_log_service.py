from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete_pattern
from app.schemas.system_log import SystemLogCreate
from app.core.timezone import get_philippine_time, to_philippine_time
from fastapi import HTTPException, status

LOGS_PAGE_TTL = 60  # 1 minute per page cache

# Sentinel values that should be treated as NULL / no suffix
_EMPTY_SENTINELS = {"{EMPTY}", "EMPTY", "NULL", "NONE", "N/A", "-", ""}

# VARCHAR limits matching the actual DB columns
_ACTIVITY_TYPE_MAX_LEN = 10   # run: ALTER TABLE system_logs ALTER COLUMN activity_type TYPE VARCHAR(10);
_SUFFIX_MAX_LEN = 5           # employees.employee_suffix and system_logs.employee_suffix


class SystemLogService:
    def __init__(self):
        pass

    def _get_username(self, user_id: int) -> str:
        """Lookup username from users table by user_id."""
        try:
            result = db_fetch_one(
                "SELECT username FROM users WHERE user_id = :user_id",
                {"user_id": user_id}
            )
            if result.data:
                return result.data[0].get("username")
        except Exception:
            pass
        return None

    def _convert_log_times(self, logs: list) -> list:
        """Convert log_time to Philippine time for a list of logs."""
        for log in logs:
            if log.get('log_time'):
                try:
                    ph_time = to_philippine_time(log['log_time'])
                    log['log_time'] = ph_time.isoformat()
                except Exception:
                    pass
        return logs

    def _sanitize_activity_type(self, activity_type: str) -> str:
        """
        Normalize activity_type and hard-truncate to VARCHAR(10).

        The DB column was originally VARCHAR(5) which was too short for
        DELETE (6), STOCK_IN (8), STOCK_OUT (9), UPLOAD (6), ARCHIVE (7).
        After running the migration (ALTER COLUMN activity_type TYPE VARCHAR(10))
        this is a safety net only.
        """
        value = (activity_type or "").strip().upper()
        return value[:_ACTIVITY_TYPE_MAX_LEN]

    def _sanitize_suffix(self, suffix) -> str | None:
        """
        FIX: Convert bad sentinel values and over-length strings to NULL.

        The employee_suffix column is VARCHAR(5). Some employees were saved
        with the literal string '{EMPTY}' (7 chars) which causes a
        StringDataRightTruncation error every time a log is written for them.

        Sentinel values like '{EMPTY}', 'NULL', '' are all returned as None
        so PostgreSQL stores a proper NULL instead.
        """
        if suffix is None:
            return None
        cleaned = str(suffix).strip()
        if cleaned.upper() in _EMPTY_SENTINELS:
            return None
        # Hard-truncate anything still too long so it never crashes
        if len(cleaned) > _SUFFIX_MAX_LEN:
            cleaned = cleaned[:_SUFFIX_MAX_LEN]
        return cleaned or None

    async def create_log(self, log_data: SystemLogCreate):
        try:
            username = log_data.username or self._get_username(log_data.user_id)

            # FIX 1: Sanitize activity_type to prevent VARCHAR overflow
            safe_activity_type = self._sanitize_activity_type(log_data.activity_type)

            # FIX 2: Sanitize employee_suffix — '{EMPTY}' (7 chars) stored in
            #         the DB was overflowing the VARCHAR(5) column on every
            #         log write, causing the 500 on PUT /payrolls/:id
            safe_suffix = self._sanitize_suffix(log_data.employee_suffix)

            result = db_execute(
                """
                INSERT INTO system_logs (
                    user_id, username, activity_type, log_time, employee_id,
                    employee_name_fn, employee_name_mi, employee_name_ln, employee_suffix,
                    payroll_id, description
                ) VALUES (
                    :user_id, :username, :activity_type, :log_time, :employee_id,
                    :employee_name_fn, :employee_name_mi, :employee_name_ln, :employee_suffix,
                    :payroll_id, :description
                ) RETURNING *
                """,
                {
                    "user_id": log_data.user_id,
                    "username": username,
                    "activity_type": safe_activity_type,
                    "log_time": get_philippine_time().isoformat(),
                    "employee_id": log_data.employee_id,
                    "employee_name_fn": log_data.employee_name_fn,
                    "employee_name_mi": log_data.employee_name_mi,
                    "employee_name_ln": log_data.employee_name_ln,
                    "employee_suffix": safe_suffix,
                    "payroll_id": log_data.payroll_id,
                    "description": log_data.description
                }
            )

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create log"
                )

            cache_delete_pattern("logs:page:*")
            return result.data[0]

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create log: {str(e)}"
            )

    async def get_all_logs(
        self,
        activity_type: str = None,
        user_id: int = None,
        employee_id: int = None,
        page: int = 1,
        limit: int = 5,
    ):
        try:
            cache_key = f"logs:page:{page}:{limit}:{activity_type or 'all'}:{user_id or 'all'}:{employee_id or 'all'}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            conditions = ["activity_type NOT IN ('STOCK_IN', 'STOCK_OUT')"]
            params = {}

            if activity_type:
                conditions.append("activity_type = :activity_type")
                params["activity_type"] = activity_type.upper()
            if user_id:
                conditions.append("user_id = :user_id")
                params["user_id"] = user_id
            if employee_id:
                conditions.append("employee_id = :employee_id")
                params["employee_id"] = employee_id

            where = " AND ".join(conditions)

            count_result = db_fetch_one(
                f"SELECT COUNT(*) as total FROM system_logs WHERE {where}",
                params
            )
            total = count_result.data[0]["total"] if count_result.data else 0

            offset = (page - 1) * limit
            params["limit"] = limit
            params["offset"] = offset

            result = db_fetch_all(
                f"""
                SELECT * FROM system_logs
                WHERE {where}
                ORDER BY log_time DESC
                LIMIT :limit OFFSET :offset
                """,
                params
            )

            logs = self._convert_log_times(result.data)
            total_pages = (total + limit - 1) // limit

            response = {
                "logs": logs,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }

            cache_set(cache_key, response, LOGS_PAGE_TTL)
            return response

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch logs: {str(e)}"
            )

    async def get_user_activity(self, user_id: int):
        try:
            result = db_fetch_all(
                "SELECT * FROM system_logs WHERE user_id = :user_id ORDER BY log_time DESC",
                {"user_id": user_id}
            )
            return {"logs": self._convert_log_times(result.data), "total": len(result.data)}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch user activity: {str(e)}"
            )

    async def get_employee_history(self, employee_id: int):
        try:
            result = db_fetch_all(
                "SELECT * FROM system_logs WHERE employee_id = :employee_id ORDER BY log_time DESC",
                {"employee_id": employee_id}
            )
            return {"logs": self._convert_log_times(result.data), "total": len(result.data)}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employee history: {str(e)}"
            )