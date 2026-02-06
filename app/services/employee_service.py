from app.core.supabase_client import get_supabase
from app.schemas.employee import EmployeeCreate
from fastapi import HTTPException, status


class EmployeeService:
    def __init__(self):
        self.supabase = get_supabase()
    
    async def get_all_employees(self):
        """Get all employees from database"""
        try:
            result = self.supabase.table('employees').select('*').execute()
            
            return {
                "employees": result.data,
                "total": len(result.data)
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employees: {str(e)}"
            )
    
    async def get_employee_by_id(self, employee_id: int):
        """Get single employee by ID"""
        try:
            result = self.supabase.table('employees').select('*').eq('employee_id', employee_id).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Employee with ID {employee_id} not found"
                )
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employee: {str(e)}"
            )
    
    async def create_employee(self, employee_data: EmployeeCreate, created_by_user_id: int):
        """Create new employee"""
        try:
            # Prepare employee data
            new_employee = {
                "employee_name_fn": employee_data.employee_name_fn,
                "employee_name_mi": employee_data.employee_name_mi,
                "employee_name_ln": employee_data.employee_name_ln,
                "employee_suffix": employee_data.employee_suffix,
                "employee_position": employee_data.employee_position,
                "basic_pay": employee_data.basic_pay,
                "salary_rate": employee_data.salary_rate,
                "salary": employee_data.salary,
                "sss_deduction": employee_data.sss_deduction,
                "phic_deduction": employee_data.phic_deduction,
                "pagibig_deduction": employee_data.pagibig_deduction,
                "created_by": created_by_user_id
            }
            
            result = self.supabase.table('employees').insert(new_employee).execute()
            
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create employee"
                )
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create employee: {str(e)}"
            )
    
    async def update_employee(self, employee_id: int, employee_data: dict):
        """Update employee"""
        try:
            # Check if employee exists
            existing = self.supabase.table('employees').select('*').eq('employee_id', employee_id).execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Employee with ID {employee_id} not found"
                )
            
            # Update employee
            result = self.supabase.table('employees').update(employee_data).eq('employee_id', employee_id).execute()
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update employee: {str(e)}"
            )
    
    async def delete_employee(self, employee_id: int):
        """Delete employee"""
        try:
            # Check if employee exists
            existing = self.supabase.table('employees').select('*').eq('employee_id', employee_id).execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Employee with ID {employee_id} not found"
                )
            
            # Delete employee
            self.supabase.table('employees').delete().eq('employee_id', employee_id).execute()
            
            return {"message": f"Employee {employee_id} deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete employee: {str(e)}"
            )