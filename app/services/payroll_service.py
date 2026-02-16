from app.core.supabase_client import get_supabase
from app.schemas.payroll import PayrollCreate, PayrollUpdate
from app.schemas.system_log import SystemLogCreate
from app.services.system_log_service import SystemLogService
from fastapi import HTTPException, status


class PayrollService:
    def __init__(self):
        self.supabase = get_supabase()
        self.log_service = SystemLogService()
    
    async def get_all_payrolls(self, employee_id: int = None, pay_status: str = None):
        """Get all payroll records with optional filters"""
        try:
            query = self.supabase.table('payrolls').select('*').order('created_at', desc=True)
            
            if employee_id:
                query = query.eq('employee_id', employee_id)
            
            if pay_status:
                query = query.eq('pay_status', pay_status)
            
            result = query.execute()
            
            return {
                "payrolls": result.data,
                "total": len(result.data),
                "employee_id_filter": employee_id if employee_id else None,
                "pay_status_filter": pay_status if pay_status else None
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch payrolls: {str(e)}"
            )
    
    async def get_payroll_by_id(self, payroll_id: int):
        """Get single payroll record by ID"""
        try:
            result = self.supabase.table('payrolls').select('*').eq('payroll_id', payroll_id).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Payroll with ID {payroll_id} not found"
                )
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch payroll: {str(e)}"
            )
    
    async def create_payroll(self, payroll_data: PayrollCreate, created_by_user_id: int):
        """
        Create new payroll with AUTO-CALCULATIONS
        
        USER INPUTS:
        - period_start_date, period_end_date
        - working_days, days_worked
        - ot_hours, no_of_absents
        - tardiness_per_minute
        - other_deductions
        - pay_status
        
        AUTO-CALCULATED:
        - basic_pay (from employee)
        - salary_rate = basic_pay / working_days
        - salary = salary_rate / 8
        - tardiness_deduction = (salary / 60) * tardiness_per_minute
        - total_deduction = sss + phic + pagibig + tardiness + other
        - gross_pay = salary_rate * days_worked
        - net_pay = gross_pay - total_deduction
        """
        try:
            # ✅ Get employee info and deductions
            employee_check = self.supabase.table('employees').select(
                'employee_id, employee_name_fn, employee_name_mi, employee_name_ln, employee_suffix, '
                'basic_pay, sss_deduction, phic_deduction, pagibig_deduction'
            ).eq('employee_id', payroll_data.employee_id).execute()
            
            if not employee_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Employee with ID {payroll_data.employee_id} not found"
                )
            
            emp = employee_check.data[0]
            
            # ✅ Get next payroll_id
            existing_payrolls = self.supabase.table('payrolls').select('payroll_id').order('payroll_id', desc=True).limit(1).execute()
            
            next_id = 1
            if existing_payrolls.data:
                next_id = existing_payrolls.data[0]['payroll_id'] + 1
            
            # ✅ Get values from employee and user input
            basic_pay = float(emp.get('basic_pay') or 0)
            employee_sss = float(emp.get('sss_deduction') or 0)
            employee_phic = float(emp.get('phic_deduction') or 0)
            employee_pagibig = float(emp.get('pagibig_deduction') or 0)
            
            working_days = int(payroll_data.working_days or 0)
            days_worked = float(payroll_data.days_worked or 0)
            no_of_absents = int(payroll_data.no_of_absents or 0)  # ✅ ADD THIS
            hours_worked = float(payroll_data.hours_worked or 0) 
            ot_hours = float(payroll_data.ot_hours or 0)
            tardiness_per_minute = int(payroll_data.tardiness_per_minute or 0)
            other_deductions = float(payroll_data.other_deductions or 0)
            
            # ✅ FORMULA 1: salary_rate (per day) = basic_pay / working_days
            salary_rate = basic_pay / working_days if working_days > 0 else 0
            
            # ✅ FORMULA 2: salary (per hour) = salary_rate / 8
            salary = salary_rate / 8
            
            # ✅ FORMULA 3: tardiness_deduction = (salary / 60) * tardiness_per_minute
            tardiness_deduction = (salary / 60) * tardiness_per_minute

            # ✅ FORMULA 4 (NEW): absent_deduction = no_of_absents * salary_rate
            absent_deduction = no_of_absents * salary_rate

            # ✅ FORMULA 5 (UPDATED): total_deduction = sss + phic + pagibig + tardiness + absent + other
            total_deduction = employee_sss + employee_phic + employee_pagibig + tardiness_deduction + absent_deduction + other_deductions
            
            # ✅ FORMULA 5: gross_pay = salary_rate * days_worked
            gross_pay = salary_rate * days_worked
            
            # ✅ FORMULA 6: net_pay = gross_pay - total_deduction
            net_pay = gross_pay - total_deduction
            
            new_payroll = {
                "payroll_id": next_id,
                "employee_id": payroll_data.employee_id,
                "days_worked": days_worked,
                "ot_hours": ot_hours,
                "no_of_absents": no_of_absents,  # ✅ CHANGED: use variable instead of payroll_data
                "hours_worked": hours_worked,  # ✅ NEW: Add this line
                "tardiness_per_minute": tardiness_per_minute,
                "tardiness_deduction": round(tardiness_deduction, 2),  # ✅ AUTO
                "absent_deduction": round(absent_deduction, 2),  # ✅ NEW: Add this line
                "period_start_date": payroll_data.period_start_date.isoformat() if payroll_data.period_start_date else None,
                "period_end_date": payroll_data.period_end_date.isoformat() if payroll_data.period_end_date else None,
                "other_deductions": other_deductions,
                "deduction_reason": payroll_data.deduction_reason,
                "total_deduction": round(total_deduction, 2),  # ✅ AUTO
                "gross_pay": round(gross_pay, 2),  # ✅ AUTO
                "net_pay": round(net_pay, 2),  # ✅ AUTO
                "working_days": working_days,
                "made_by": created_by_user_id,
                "salary_rate": round(salary_rate, 2),  # ✅ AUTO
                "salary": round(salary, 2),  # ✅ AUTO
                "pay_status": payroll_data.pay_status or "Pending"
            }
            
            result = self.supabase.table('payrolls').insert(new_payroll).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create payroll"
                )
            
            created_payroll = result.data[0]
            
            # ✅ Create system log
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create payroll: {str(e)}"
            )
    
    async def update_payroll(self, payroll_id: int, payroll_data: dict, updated_by_user_id: int):
        """Update payroll record and log the EDIT action"""
        try:
            existing = self.supabase.table('payrolls').select('*, employees(employee_name_fn, employee_name_mi, employee_name_ln, employee_suffix, basic_pay, sss_deduction, phic_deduction, pagibig_deduction)').eq('payroll_id', payroll_id).execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Payroll with ID {payroll_id} not found"
                )
            
            payroll_record = existing.data[0]
            emp = payroll_record.get('employees', {})
            
            # ✅ Recalculate if working_days or days_worked changed
            if 'working_days' in payroll_data or 'days_worked' in payroll_data or 'tardiness_per_minute' in payroll_data or 'other_deductions' in payroll_data:
                basic_pay = float(emp.get('basic_pay') or 0)
                employee_sss = float(emp.get('sss_deduction') or 0)
                employee_phic = float(emp.get('phic_deduction') or 0)
                employee_pagibig = float(emp.get('pagibig_deduction') or 0)
                
                working_days = int(payroll_data.get('working_days', payroll_record.get('working_days', 0)))
                days_worked = float(payroll_data.get('days_worked', payroll_record.get('days_worked', 0)))
                no_of_absents = int(payroll_data.get('no_of_absents', payroll_record.get('no_of_absents', 0)))  # ✅ ADD THIS
                hours_worked = float(payroll_data.get('hours_worked', payroll_record.get('hours_worked', 0)))  # ✅ ADD THIS
                tardiness_per_minute = int(payroll_data.get('tardiness_per_minute', payroll_record.get('tardiness_per_minute', 0)))
                other_deductions = float(payroll_data.get('other_deductions', payroll_record.get('other_deductions', 0)))
                
                # Recalculate formulas
                salary_rate = basic_pay / working_days if working_days > 0 else 0
                salary = salary_rate / 8
                tardiness_deduction = (salary / 60) * tardiness_per_minute
                absent_deduction = no_of_absents * salary_rate  # ✅ ADD THIS
                total_deduction = employee_sss + employee_phic + employee_pagibig + tardiness_deduction + absent_deduction + other_deductions  # ✅ UPDATED
                gross_pay = salary_rate * days_worked
                net_pay = gross_pay - total_deduction
                
                # Update calculated fields
                payroll_data['salary_rate'] = round(salary_rate, 2)
                payroll_data['salary'] = round(salary, 2)
                payroll_data['tardiness_deduction'] = round(tardiness_deduction, 2)
                payroll_data['absent_deduction'] = round(absent_deduction, 2)  # ✅ ADD THIS LINE
                payroll_data['total_deduction'] = round(total_deduction, 2)
                payroll_data['gross_pay'] = round(gross_pay, 2)
                payroll_data['net_pay'] = round(net_pay, 2)
            
            if 'period_start_date' in payroll_data and payroll_data['period_start_date']:
                payroll_data['period_start_date'] = payroll_data['period_start_date'].isoformat() if hasattr(payroll_data['period_start_date'], 'isoformat') else payroll_data['period_start_date']
            
            if 'period_end_date' in payroll_data and payroll_data['period_end_date']:
                payroll_data['period_end_date'] = payroll_data['period_end_date'].isoformat() if hasattr(payroll_data['period_end_date'], 'isoformat') else payroll_data['period_end_date']
            
            result = self.supabase.table('payrolls').update(payroll_data).eq('payroll_id', payroll_id).execute()
            
            await self.log_service.create_log(SystemLogCreate(
                user_id=updated_by_user_id,
                activity_type="EDIT",
                employee_id=payroll_record['employee_id'],
                employee_name_fn=emp.get('employee_name_fn'),
                employee_name_mi=emp.get('employee_name_mi'),
                employee_name_ln=emp.get('employee_name_ln'),
                employee_suffix=emp.get('employee_suffix'),
                payroll_id=payroll_id
            ))
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update payroll: {str(e)}"
            )
    
    async def delete_payroll(self, payroll_id: int, deleted_by_user_id: int):
        """Delete payroll record and log the DELETE action"""
        try:
            existing = self.supabase.table('payrolls').select('*, employees(employee_name_fn, employee_name_mi, employee_name_ln, employee_suffix)').eq('payroll_id', payroll_id).execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Payroll with ID {payroll_id} not found"
                )
            
            payroll = existing.data[0]
            emp = payroll.get('employees', {})
            
            self.supabase.table('payrolls').delete().eq('payroll_id', payroll_id).execute()
            
            await self.log_service.create_log(SystemLogCreate(
                user_id=deleted_by_user_id,
                activity_type="DELETE",
                employee_id=payroll['employee_id'],
                employee_name_fn=emp.get('employee_name_fn'),
                employee_name_mi=emp.get('employee_name_mi'),
                employee_name_ln=emp.get('employee_name_ln'),
                employee_suffix=emp.get('employee_suffix'),
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete payroll: {str(e)}"
            )