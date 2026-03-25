from app.core.db_client import db_fetch_all, db_fetch_one, db_execute, cache_get, cache_set, cache_delete, cache_delete_pattern
from app.schemas.payroll import PayrollCreate, PayrollUpdate
from app.schemas.system_log import SystemLogCreate
from app.services.system_log_service import SystemLogService
from fastapi import HTTPException, status

PAYROLLS_TTL = 180    # 3 minutes — payroll data changes more frequently
PAYROLL_TTL = 300     # 5 minutes

# Fields that come from the JOIN but must never be written back to the payrolls table
_NON_PAYROLL_FIELDS = (
    'employee_name_fn', 'employee_name_mi', 'employee_name_ln', 'employee_suffix',
    'basic_pay', 'sss_deduction', 'phic_deduction', 'pagibig_deduction',
)


class PayrollService:
    def __init__(self):
        self.log_service = SystemLogService()

    async def get_all_payrolls(self, employee_id: int = None, pay_status: str = None):
        try:
            # Cache key includes filters
            cache_key = f"payrolls:list:{employee_id or 'all'}:{pay_status or 'all'}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            conditions = ["1=1"]
            params = {}

            if employee_id:
                conditions.append("p.employee_id = :employee_id")
                params["employee_id"] = employee_id
            if pay_status:
                conditions.append("p.pay_status = :pay_status")
                params["pay_status"] = pay_status

            where = " AND ".join(conditions)

            # JOIN with employees to get name in one query
            result = db_fetch_all(
                f"""
                SELECT
                    p.*,
                    e.employee_name_fn, e.employee_name_mi,
                    e.employee_name_ln, e.employee_suffix
                FROM payrolls p
                JOIN employees e ON e.employee_id = p.employee_id
                WHERE {where}
                ORDER BY p.created_at DESC
                """,
                params
            )

            response = {
                "payrolls": result.data,
                "total": len(result.data),
                "employee_id_filter": employee_id if employee_id else None,
                "pay_status_filter": pay_status if pay_status else None
            }

            cache_set(cache_key, response, PAYROLLS_TTL)
            return response

        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch payrolls: {str(e)}")

    async def get_payroll_by_id(self, payroll_id: int):
        try:
            cache_key = f"payrolls:{payroll_id}"
            cached = cache_get(cache_key)
            if cached:
                return cached

            result = db_fetch_one(
                """
                SELECT p.*, e.employee_name_fn, e.employee_name_mi,
                       e.employee_name_ln, e.employee_suffix
                FROM payrolls p
                JOIN employees e ON e.employee_id = p.employee_id
                WHERE p.payroll_id = :payroll_id
                """,
                {"payroll_id": payroll_id}
            )
            if not result.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payroll with ID {payroll_id} not found")

            payroll = result.data[0]
            cache_set(cache_key, payroll, PAYROLL_TTL)
            return payroll

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch payroll: {str(e)}")

    async def create_payroll(self, payroll_data: PayrollCreate, created_by_user_id: int):
        try:
            employee_check = db_fetch_one(
                """
                SELECT employee_id, employee_name_fn, employee_name_mi, employee_name_ln,
                       employee_suffix, basic_pay, sss_deduction, phic_deduction, pagibig_deduction
                FROM employees WHERE employee_id = :employee_id
                """,
                {"employee_id": payroll_data.employee_id}
            )

            if not employee_check.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Employee with ID {payroll_data.employee_id} not found")

            emp = employee_check.data[0]

            # Payroll calculations
            basic_pay = float(emp.get('basic_pay') or 0)
            employee_sss = float(emp.get('sss_deduction') or 0)
            employee_phic = float(emp.get('phic_deduction') or 0)
            employee_pagibig = float(emp.get('pagibig_deduction') or 0)

            working_days = int(payroll_data.working_days or 0)
            days_worked = float(payroll_data.days_worked or 0)
            no_of_absents = int(payroll_data.no_of_absents or 0)
            hours_worked = float(payroll_data.hours_worked or 0)
            ot_hours = float(payroll_data.ot_hours or 0)
            tardiness_per_minute = int(payroll_data.tardiness_per_minute or 0)
            other_deductions = float(payroll_data.other_deductions or 0)

            salary_rate = basic_pay / working_days if working_days > 0 else 0
            salary = salary_rate / 8
            tardiness_deduction = (salary / 60) * tardiness_per_minute
            absent_deduction = no_of_absents * salary_rate
            total_deduction = employee_sss + employee_phic + employee_pagibig + tardiness_deduction + absent_deduction + other_deductions
            gross_pay = salary_rate * days_worked
            net_pay = gross_pay - total_deduction

            # No manual ID generation — let DB handle it with SERIAL
            result = db_execute(
                """
                INSERT INTO payrolls (
                    employee_id, days_worked, ot_hours, no_of_absents, hours_worked,
                    tardiness_per_minute, tardiness_deduction, absent_deduction,
                    period_start_date, period_end_date, other_deductions, deduction_reason,
                    total_deduction, gross_pay, net_pay, working_days, made_by,
                    salary_rate, salary, pay_status
                ) VALUES (
                    :employee_id, :days_worked, :ot_hours, :no_of_absents, :hours_worked,
                    :tardiness_per_minute, :tardiness_deduction, :absent_deduction,
                    :period_start_date, :period_end_date, :other_deductions, :deduction_reason,
                    :total_deduction, :gross_pay, :net_pay, :working_days, :made_by,
                    :salary_rate, :salary, :pay_status
                ) RETURNING *
                """,
                {
                    "employee_id": payroll_data.employee_id,
                    "days_worked": days_worked,
                    "ot_hours": ot_hours,
                    "no_of_absents": no_of_absents,
                    "hours_worked": hours_worked,
                    "tardiness_per_minute": tardiness_per_minute,
                    "tardiness_deduction": round(tardiness_deduction, 2),
                    "absent_deduction": round(absent_deduction, 2),
                    "period_start_date": payroll_data.period_start_date.isoformat() if payroll_data.period_start_date else None,
                    "period_end_date": payroll_data.period_end_date.isoformat() if payroll_data.period_end_date else None,
                    "other_deductions": other_deductions,
                    "deduction_reason": payroll_data.deduction_reason,
                    "total_deduction": round(total_deduction, 2),
                    "gross_pay": round(gross_pay, 2),
                    "net_pay": round(net_pay, 2),
                    "working_days": working_days,
                    "made_by": created_by_user_id,
                    "salary_rate": round(salary_rate, 2),
                    "salary": round(salary, 2),
                    "pay_status": payroll_data.pay_status or "Pending"
                }
            )

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create payroll")

            created_payroll = result.data[0]

            # Invalidate payroll list caches
            cache_delete_pattern("payrolls:list:*")

            await self.log_service.create_log(SystemLogCreate(
                user_id=created_by_user_id,
                activity_type="ADD",
                employee_id=payroll_data.employee_id,
                employee_name_fn=emp['employee_name_fn'],
                employee_name_mi=emp['employee_name_mi'],
                employee_name_ln=emp['employee_name_ln'],
                employee_suffix=emp['employee_suffix'],
                payroll_id=created_payroll['payroll_id']
            ))

            return created_payroll

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create payroll: {str(e)}")

    async def update_payroll(self, payroll_id: int, payroll_data: dict, updated_by_user_id: int):
        try:
            existing = db_fetch_one(
                """
                SELECT p.*, e.employee_name_fn, e.employee_name_mi, e.employee_name_ln,
                       e.employee_suffix, e.basic_pay, e.sss_deduction, e.phic_deduction, e.pagibig_deduction
                FROM payrolls p
                JOIN employees e ON e.employee_id = p.employee_id
                WHERE p.payroll_id = :payroll_id
                """,
                {"payroll_id": payroll_id}
            )

            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payroll with ID {payroll_id} not found")

            payroll_record = existing.data[0]

            # Recalculate derived fields if any calculation-affecting field was sent
            if any(k in payroll_data for k in ('working_days', 'days_worked', 'tardiness_per_minute', 'other_deductions', 'no_of_absents', 'hours_worked')):
                basic_pay = float(payroll_record.get('basic_pay') or 0)
                employee_sss = float(payroll_record.get('sss_deduction') or 0)
                employee_phic = float(payroll_record.get('phic_deduction') or 0)
                employee_pagibig = float(payroll_record.get('pagibig_deduction') or 0)

                working_days = int(payroll_data.get('working_days', payroll_record.get('working_days', 0)))
                days_worked = float(payroll_data.get('days_worked', payroll_record.get('days_worked', 0)))
                no_of_absents = int(payroll_data.get('no_of_absents', payroll_record.get('no_of_absents', 0)))
                hours_worked = float(payroll_data.get('hours_worked', payroll_record.get('hours_worked', 0)))
                tardiness_per_minute = int(payroll_data.get('tardiness_per_minute', payroll_record.get('tardiness_per_minute', 0)))
                other_deductions = float(payroll_data.get('other_deductions', payroll_record.get('other_deductions', 0)))

                salary_rate = basic_pay / working_days if working_days > 0 else 0
                salary = salary_rate / 8
                tardiness_deduction = (salary / 60) * tardiness_per_minute
                absent_deduction = no_of_absents * salary_rate
                total_deduction = employee_sss + employee_phic + employee_pagibig + tardiness_deduction + absent_deduction + other_deductions
                gross_pay = salary_rate * days_worked
                net_pay = gross_pay - total_deduction

                payroll_data['salary_rate'] = round(salary_rate, 2)
                payroll_data['salary'] = round(salary, 2)
                payroll_data['tardiness_deduction'] = round(tardiness_deduction, 2)
                payroll_data['absent_deduction'] = round(absent_deduction, 2)
                payroll_data['total_deduction'] = round(total_deduction, 2)
                payroll_data['gross_pay'] = round(gross_pay, 2)
                payroll_data['net_pay'] = round(net_pay, 2)

            # Serialize date fields
            for date_field in ('period_start_date', 'period_end_date'):
                if date_field in payroll_data and payroll_data[date_field]:
                    val = payroll_data[date_field]
                    payroll_data[date_field] = val.isoformat() if hasattr(val, 'isoformat') else val

            # ✅ FIX: Strip fields that don't belong in the payrolls table
            # (these come from the JOIN on employees and must never be written back)
            for ef in _NON_PAYROLL_FIELDS:
                payroll_data.pop(ef, None)

            # ✅ FIX: Guard against an empty update dict, which would produce
            #         "UPDATE payrolls SET  WHERE ..." — invalid SQL → 500 error
            if not payroll_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No valid fields provided for update"
                )

            set_clauses = ", ".join([f"{k} = :{k}" for k in payroll_data.keys()])
            params = {**payroll_data, "payroll_id": payroll_id}

            result = db_execute(
                f"UPDATE payrolls SET {set_clauses} WHERE payroll_id = :payroll_id RETURNING *",
                params
            )

            # ✅ FIX: Guard against an empty RETURNING result (shouldn't happen
            #         after the existence check above, but prevents an unhandled
            #         IndexError on result.data[0] if the DB returns nothing)
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Update succeeded but no data was returned from the database"
                )

            # Invalidate caches
            cache_delete(f"payrolls:{payroll_id}")
            cache_delete_pattern("payrolls:list:*")

            await self.log_service.create_log(SystemLogCreate(
                user_id=updated_by_user_id,
                activity_type="EDIT",
                employee_id=payroll_record['employee_id'],
                employee_name_fn=payroll_record.get('employee_name_fn'),
                employee_name_mi=payroll_record.get('employee_name_mi'),
                employee_name_ln=payroll_record.get('employee_name_ln'),
                employee_suffix=payroll_record.get('employee_suffix'),
                payroll_id=payroll_id
            ))

            return result.data[0]

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update payroll: {str(e)}")

    async def delete_payroll(self, payroll_id: int, deleted_by_user_id: int):
        try:
            existing = db_fetch_one(
                """
                SELECT p.*, e.employee_name_fn, e.employee_name_mi, e.employee_name_ln, e.employee_suffix
                FROM payrolls p
                JOIN employees e ON e.employee_id = p.employee_id
                WHERE p.payroll_id = :payroll_id
                """,
                {"payroll_id": payroll_id}
            )

            if not existing.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Payroll with ID {payroll_id} not found")

            payroll = existing.data[0]
            db_execute("DELETE FROM payrolls WHERE payroll_id = :payroll_id", {"payroll_id": payroll_id})

            # Invalidate caches
            cache_delete(f"payrolls:{payroll_id}")
            cache_delete_pattern("payrolls:list:*")

            await self.log_service.create_log(SystemLogCreate(
                user_id=deleted_by_user_id,
                activity_type="DELETE",
                employee_id=payroll['employee_id'],
                employee_name_fn=payroll.get('employee_name_fn'),
                employee_name_mi=payroll.get('employee_name_mi'),
                employee_name_ln=payroll.get('employee_name_ln'),
                employee_suffix=payroll.get('employee_suffix'),
                payroll_id=payroll_id
            ))

            return {
                "message": f"Payroll {payroll_id} deleted successfully",
                "payroll_id": payroll_id,
                "employee_id": payroll['employee_id'],
                "deleted_by": deleted_by_user_id
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete payroll: {str(e)}")