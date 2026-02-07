from app.core.supabase_client import get_supabase
from app.schemas.employee import EmployeeCreate, EmployeeUpdate
from app.schemas.system_log import SystemLogCreate
from app.services.system_log_service import SystemLogService
from fastapi import HTTPException, status


class EmployeeService:
    def __init__(self):
        self.supabase = get_supabase()
        self.log_service = SystemLogService()
    
    async def get_all_employees(self, search: str = None, status: str = None):
        """
        Get all employees from database with optional filters
        
        Args:
            search: Search term for employee names (first, middle, last)
            status: Filter by employment status (Regular, Probationary, Contractual, Project-based)
        
        Returns:
            Dictionary with employees list, total count, and filter info
        """
        try:
            query = self.supabase.table('employees').select('*')
            
            # Filter by status if provided
            if status:
                query = query.eq('employee_status', status)
            
            # Search by name if provided
            if search:
                search_term = search.strip().upper()
                query = query.or_(
                    f"employee_name_fn.ilike.%{search_term}%,"
                    f"employee_name_mi.ilike.%{search_term}%,"
                    f"employee_name_ln.ilike.%{search_term}%"
                )
            
            result = query.execute()
            
            return {
                "employees": result.data,
                "total": len(result.data),
                "search": search if search else None,
                "status_filter": status if status else None
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch employees: {str(e)}"
            )
    
    async def get_employee_by_id(self, employee_id: int):
        """
        Get single employee by ID
        
        Args:
            employee_id: The employee ID to fetch
        
        Returns:
            Employee data dictionary
        
        Raises:
            404: Employee not found
        """
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
        """
        Create new employee and log the ADD action
        
        Args:
            employee_data: Employee information from request
            created_by_user_id: User ID of the admin creating the employee
        
        Returns:
            Created employee data
        
        Features:
            - Auto-generates next employee_id
            - Validates required fields (first name, last name)
            - Sets default status to "Regular" if not provided
            - Creates system log with all name components (fn, mi, ln, suffix)
        """
        try:
            # Get next available employee_id
            existing_employees = self.supabase.table('employees').select('employee_id').order('employee_id', desc=True).limit(1).execute()
            
            next_id = 1
            if existing_employees.data:
                next_id = existing_employees.data[0]['employee_id'] + 1
            
            new_employee = {
                "employee_id": next_id,
                "employee_name_fn": employee_data.employee_name_fn,
                "employee_name_mi": employee_data.employee_name_mi,
                "employee_name_ln": employee_data.employee_name_ln,
                "employee_suffix": employee_data.employee_suffix,
                "employee_position": employee_data.employee_position,
                "employee_status": employee_data.employee_status or "Regular",
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
            
            created_employee = result.data[0]
            
            # Create system log with all name components (independent storage, no foreign key)
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create employee: {str(e)}"
            )
    
    async def update_employee(self, employee_id: int, employee_data: dict, updated_by_user_id: int):
        """
        Update employee and log the EDIT action
        
        Args:
            employee_id: The employee ID to update
            employee_data: Dictionary with fields to update (only provided fields)
            updated_by_user_id: User ID of the admin updating the employee
        
        Returns:
            Updated employee data
        
        Features:
            - Validates employee exists before updating
            - Supports partial updates (only provided fields)
            - Creates system log with current name components (fn, mi, ln, suffix)
        
        Raises:
            404: Employee not found
        """
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
            
            updated_emp = result.data[0]
            
            # Create system log with all name components
            await self.log_service.create_log(SystemLogCreate(
                user_id=updated_by_user_id,
                activity_type="EDIT",
                employee_id=employee_id,
                employee_name_fn=updated_emp['employee_name_fn'],
                employee_name_mi=updated_emp['employee_name_mi'],
                employee_name_ln=updated_emp['employee_name_ln'],
                employee_suffix=updated_emp['employee_suffix']
            ))
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update employee: {str(e)}"
            )
    
    async def delete_employee(self, employee_id: int, deleted_by_user_id: int):
        """
        Delete employee and log the DELETE action
        
        Args:
            employee_id: The employee ID to delete
            deleted_by_user_id: User ID of the admin deleting the employee
        
        Returns:
            Success message with deleted employee info
        
        Features:
            - Validates employee exists before deleting
            - CASCADE DELETE automatically removes all payroll records
            - Creates system log with all name components BEFORE deletion
            - Logs remain intact with employee info after deletion (no foreign key)
        
        Database CASCADE behavior:
            - Deletes all payroll records for this employee (payrolls table)
            - Keeps system logs intact (no foreign key relationship)
        
        System logs store:
            - employee_id (just a number, not a foreign key)
            - employee_name_fn (first name)
            - employee_name_mi (middle initial)
            - employee_name_ln (last name)
            - employee_suffix (Jr., Sr., III, etc.)
        
        Raises:
            404: Employee not found
        """
        try:
            # Check if employee exists
            existing = self.supabase.table('employees').select('*').eq('employee_id', employee_id).execute()
            
            if not existing.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Employee with ID {employee_id} not found"
                )
            
            # Get employee info BEFORE deleting (for log and response message)
            emp = existing.data[0]
            
            # Build full name with suffix for display
            full_name_parts = [
                emp['employee_name_fn'],
                emp['employee_name_mi'] if emp['employee_name_mi'] else '',
                emp['employee_name_ln']
            ]
            if emp.get('employee_suffix'):
                full_name_parts.append(emp['employee_suffix'])
            
            # Join and clean up extra spaces
            full_name = ' '.join(filter(None, full_name_parts)).strip()
            
            # Delete employee (CASCADE will auto-delete payroll records)
            self.supabase.table('employees').delete().eq('employee_id', employee_id).execute()
            
            # Create system log with all name components (employee already deleted, but we have the data!)
            # Logs are independent - no foreign key, so they remain intact forever
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
                "message": f"Employee {employee_id} ({full_name}) deleted successfully (including all payroll records)",
                "employee_id": employee_id,
                "employee_name": full_name,
                "deleted_by": deleted_by_user_id
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete employee: {str(e)}"
            )