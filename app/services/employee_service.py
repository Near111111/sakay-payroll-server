from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete, cache_delete_pattern
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.schemas.system_log import SystemLogCreate
from app.services.system_log_service import SystemLogService
from fastapi import HTTPException, status

# Cache TTL constants
EMPLOYEES_LIST_TTL = 300   # 5 minutes
EMPLOYEE_TTL = 600         # 10 minutes


class EmployeeService:
    def __init__(self):
        self.log_service = SystemLogService()

    async def get_all_employees(self, search: str = None, status: str = None):
        try:
            # ✅ Cache key includes filters so different filters cache separately
            cache_key = f"employees:list:{search or 'all'}:{status or 'all'}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            conditions = ["1=1"]
            params = {}

            if status:
                conditions.append("employee_status = :status")
                params["status"] = status

            if search:
                search_term = f"%{search.strip().upper()}%"
                conditions.append(
                    "(UPPER(employee_name_fn) LIKE :search OR UPPER(employee_name_mi) LIKE :search OR UPPER(employee_name_ln) LIKE :search)"
                )
                params["search"] = search_term

            where = " AND ".join(conditions)

            result = db_fetch_all(
                f"SELECT * FROM employees WHERE {where} ORDER BY employee_name_ln, employee_name_fn",
                params
            )

            response = {
                "employees": result.data,
                "total": len(result.data),
                "search": search if search else None,
                "status_filter": status if status else None
            }

            cache_set(cache_key, response, EMPLOYEES_LIST_TTL)
            return response

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employees: {str(e)}"
            )

    async def get_employee_by_id(self, employee_id: int):
        try:
            # ✅ Cache individual employee
            cache_key = f"employees:{employee_id}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            result = db_fetch_one(
                "SELECT * FROM employees WHERE employee_id = :employee_id",
                {"employee_id": employee_id}
            )
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Employee with ID {employee_id} not found"
                )

            employee = result.data[0]
            cache_set(cache_key, employee, EMPLOYEE_TTL)
            return employee

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employee: {str(e)}"
            )

    async def create_employee(self, employee_data: EmployeeCreate, created_by_user_id: int):
        try:
            # ✅ Use SERIAL/sequence instead of manual MAX(id)+1
            result = db_execute(
                """
                INSERT INTO employees (
                    employee_name_fn, employee_name_mi, employee_name_ln,
                    employee_suffix, employee_position, employee_status,
                    basic_pay, sss_deduction, phic_deduction, pagibig_deduction, created_by
                ) VALUES (
                    :employee_name_fn, :employee_name_mi, :employee_name_ln,
                    :employee_suffix, :employee_position, :employee_status,
                    :basic_pay, :sss_deduction, :phic_deduction, :pagibig_deduction, :created_by
                ) RETURNING *
                """,
                {
                    "employee_name_fn": employee_data.employee_name_fn,
                    "employee_name_mi": employee_data.employee_name_mi,
                    "employee_name_ln": employee_data.employee_name_ln,
                    "employee_suffix": employee_data.employee_suffix,
                    "employee_position": employee_data.employee_position,
                    "employee_status": employee_data.employee_status or "Regular",
                    "basic_pay": employee_data.basic_pay,
                    "sss_deduction": employee_data.sss_deduction,
                    "phic_deduction": employee_data.phic_deduction,
                    "pagibig_deduction": employee_data.pagibig_deduction,
                    "created_by": created_by_user_id
                }
            )

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create employee")

            created_employee = result.data[0]

            # ✅ Invalidate all employee list caches
            cache_delete_pattern("employees:list:*")

            await self.log_service.create_log(SystemLogCreate(
                user_id=created_by_user_id,
                activity_type="ADD",
                employee_id=created_employee['employee_id'],
                employee_name_fn=created_employee['employee_name_fn'],
                employee_name_mi=created_employee['employee_name_mi'],
                employee_name_ln=created_employee['employee_name_ln'],
                employee_suffix=created_employee['employee_suffix']
            ))

            return created_employee

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create employee: {str(e)}")

    async def update_employee(self, employee_id: int, employee_data: dict, updated_by_user_id: int):
        try:
            existing = db_fetch_one(
                "SELECT * FROM employees WHERE employee_id = :employee_id",
                {"employee_id": employee_id}
            )
            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Employee with ID {employee_id} not found")

            if not employee_data:
                return existing.data[0]

            set_clauses = ", ".join([f"{k} = :{k}" for k in employee_data.keys()])
            params = {**employee_data, "employee_id": employee_id}

            result = db_execute(
                f"UPDATE employees SET {set_clauses} WHERE employee_id = :employee_id RETURNING *",
                params
            )

            updated_emp = result.data[0]

            # ✅ Invalidate caches for this employee and all lists
            cache_delete(f"employees:{employee_id}")
            cache_delete_pattern("employees:list:*")

            await self.log_service.create_log(SystemLogCreate(
                user_id=updated_by_user_id,
                activity_type="EDIT",
                employee_id=employee_id,
                employee_name_fn=updated_emp['employee_name_fn'],
                employee_name_mi=updated_emp['employee_name_mi'],
                employee_name_ln=updated_emp['employee_name_ln'],
                employee_suffix=updated_emp['employee_suffix']
            ))

            return updated_emp

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update employee: {str(e)}")

    async def delete_employee(self, employee_id: int, deleted_by_user_id: int):
        try:
            existing = db_fetch_one(
                "SELECT * FROM employees WHERE employee_id = :employee_id",
                {"employee_id": employee_id}
            )
            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Employee with ID {employee_id} not found")

            emp = existing.data[0]
            full_name_parts = [
                emp['employee_name_fn'],
                emp['employee_name_mi'] if emp['employee_name_mi'] else '',
                emp['employee_name_ln']
            ]
            if emp.get('employee_suffix'):
                full_name_parts.append(emp['employee_suffix'])
            full_name = ' '.join(filter(None, full_name_parts)).strip()

            db_execute(
                "DELETE FROM employees WHERE employee_id = :employee_id",
                {"employee_id": employee_id}
            )

            # ✅ Invalidate caches
            cache_delete(f"employees:{employee_id}")
            cache_delete_pattern("employees:list:*")
            # Also invalidate payroll caches for this employee
            cache_delete_pattern(f"payrolls:list:*{employee_id}*")

            await self.log_service.create_log(SystemLogCreate(
                user_id=deleted_by_user_id,
                activity_type="DELETE",
                employee_id=employee_id,
                employee_name_fn=emp['employee_name_fn'],
                employee_name_mi=emp['employee_name_mi'],
                employee_name_ln=emp['employee_name_ln'],
                employee_suffix=emp['employee_suffix']
            ))

            return {
                "message": f"Employee {employee_id} ({full_name}) deleted successfully",
                "employee_id": employee_id,
                "employee_name": full_name,
                "deleted_by": deleted_by_user_id
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete employee: {str(e)}")