from app.core.supabase_client import get_supabase
from app.schemas.system_log import SystemLogCreate
from app.core.timezone import get_philippine_time, to_philippine_time
from fastapi import HTTPException, status


class SystemLogService:
    def __init__(self):
        self.supabase = get_supabase()

    async def create_log(self, log_data: SystemLogCreate):
        """
        Create a new system log entry
        Stores employee name components separately for history
        """
        try:
            new_log = {
                "user_id": log_data.user_id,
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

            result = self.supabase.table('system_logs').insert(new_log).execute()

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create log"
                )

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create log: {str(e)}"
            )

    async def get_all_logs(self, activity_type: str = None, user_id: int = None, employee_id: int = None):
        """Get all system logs with optional filters"""
        try:
            query = self.supabase.table('system_logs').select('*').order('log_time', desc=True)

            if activity_type:
                query = query.eq('activity_type', activity_type.upper())

            if user_id:
                query = query.eq('user_id', user_id)

            if employee_id:
                query = query.eq('employee_id', employee_id)

            result = query.execute()

            # Convert timestamps to Philippine time
            for log in result.data:
                if log.get('log_time'):
                    try:
                        ph_time = to_philippine_time(log['log_time'])
                        log['log_time'] = ph_time.isoformat()
                    except:
                        pass

            return {
                "logs": result.data,
                "total": len(result.data)
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch logs: {str(e)}"
            )

    async def get_user_activity(self, user_id: int):
        """Get all activities by a specific user"""
        try:
            result = self.supabase.table('system_logs').select('*').eq('user_id', user_id).order('log_time',
                                                                                                 desc=True).execute()

            for log in result.data:
                if log.get('log_time'):
                    try:
                        ph_time = to_philippine_time(log['log_time'])
                        log['log_time'] = ph_time.isoformat()
                    except:
                        pass

            return {
                "logs": result.data,
                "total": len(result.data)
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch user activity: {str(e)}"
            )

    async def get_employee_history(self, employee_id: int):
        """Get all activities related to a specific employee"""
        try:
            result = self.supabase.table('system_logs').select('*').eq('employee_id', employee_id).order('log_time',
                                                                                                         desc=True).execute()

            for log in result.data:
                if log.get('log_time'):
                    try:
                        ph_time = to_philippine_time(log['log_time'])
                        log['log_time'] = ph_time.isoformat()
                    except:
                        pass

            return {
                "logs": result.data,
                "total": len(result.data)
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employee history: {str(e)}"
            )