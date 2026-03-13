from app.core.db_client import db_fetch_all, db_execute
from app.schemas.system_log import SystemLogCreate
from app.core.timezone import get_philippine_time, to_philippine_time
from fastapi import HTTPException, status


class SystemLogService:
    def __init__(self):
        pass

    async def create_log(self, log_data: SystemLogCreate):
        try:
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
                    "username": log_data.username,  # ✅ Added
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
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create log")

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create log: {str(e)}")

    async def get_all_logs(self, activity_type: str = None, user_id: int = None, employee_id: int = None):
        try:
            conditions = ["1=1"]
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
            result = db_fetch_all(f"SELECT * FROM system_logs WHERE {where} ORDER BY log_time DESC", params)

            for log in result.data:
                if log.get('log_time'):
                    try:
                        ph_time = to_philippine_time(log['log_time'])
                        log['log_time'] = ph_time.isoformat()
                    except Exception:
                        pass

            return {"logs": result.data, "total": len(result.data)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch logs: {str(e)}")

    async def get_user_activity(self, user_id: int):
        try:
            result = db_fetch_all(
                "SELECT * FROM system_logs WHERE user_id = :user_id ORDER BY log_time DESC",
                {"user_id": user_id}
            )
            for log in result.data:
                if log.get('log_time'):
                    try:
                        ph_time = to_philippine_time(log['log_time'])
                        log['log_time'] = ph_time.isoformat()
                    except Exception:
                        pass
            return {"logs": result.data, "total": len(result.data)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch user activity: {str(e)}")

    async def get_employee_history(self, employee_id: int):
        try:
            result = db_fetch_all(
                "SELECT * FROM system_logs WHERE employee_id = :employee_id ORDER BY log_time DESC",
                {"employee_id": employee_id}
            )
            for log in result.data:
                if log.get('log_time'):
                    try:
                        ph_time = to_philippine_time(log['log_time'])
                        log['log_time'] = ph_time.isoformat()
                    except Exception:
                        pass
            return {"logs": result.data, "total": len(result.data)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch employee history: {str(e)}")