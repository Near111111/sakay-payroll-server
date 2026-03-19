from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete_pattern
from app.schemas.system_log import SystemLogCreate
from app.core.timezone import get_philippine_time, to_philippine_time
from fastapi import HTTPException, status

LOGS_PAGE_TTL = 60  # 1 minute per page cache


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

    async def create_log(self, log_data: SystemLogCreate):
        try:
            username = log_data.username or self._get_username(log_data.user_id)

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
                    "activity_type": log_data.activity_type,
                    "log_time": get_philippine_time().isoformat(),
                    "employee_id": log_data.employee_id,
                    "employee_name_fn": log_data.employee_name_fn,
                    "employee_name_mi": log_data.employee_name_mi,
                    "employee_name_ln": log_data.employee_name_ln,
                    "employee_suffix": log_data.employee_suffix,
                    "payroll_id": log_data.payroll_id,
                    "description": log_data.description
                }
            )

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create log"
                )

            # ✅ Invalidate log page caches when a new log is created
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
            # ✅ Cache key includes all filter params + page
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

            # ✅ Get total count first (for pagination metadata)
            count_result = db_fetch_one(
                f"SELECT COUNT(*) as total FROM system_logs WHERE {where}",
                params
            )
            total = count_result.data[0]["total"] if count_result.data else 0

            # ✅ Fetch only the current page
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

            total_pages = (total + limit - 1) // limit  # ceiling division

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