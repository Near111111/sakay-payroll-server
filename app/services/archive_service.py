from app.core.supabase_client import get_supabase
from app.schemas.archive import ArchiveReportCreate
from fastapi import HTTPException, status
from datetime import datetime


class ArchiveService:
    def __init__(self):
        self.supabase = get_supabase()

    async def create_archive(self, archive_date: str, user_id: int, username: str):
        """
        Archive all current payrolls:
        1. Look up current period approval status
        2. Create archive_report entry with approval status
        3. Copy all payrolls with employee data to archive_payrolls
        4. Delete all payrolls from payrolls table
        5. Clean up the payroll_approvals record
        """
        try:
            # STEP 1: Get all payrolls first to find the period
            payrolls = self.supabase.table('payrolls').select(
                '*, employees(employee_name_fn, employee_name_mi, employee_name_ln, '
                'employee_suffix, employee_position, sss_deduction, phic_deduction, '
                'pagibig_deduction, basic_pay)'
            ).execute()

            if not payrolls.data or len(payrolls.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No payrolls to archive"
                )

            # Try to find approval status for the period
            approval_data = {
                "approved_by_accounting": False,
                "approved_by_ceo": False,
                "accounting_approved_at": None,
                "ceo_approved_at": None,
            }
            first_payroll = payrolls.data[0]
            p_start = first_payroll.get('period_start_date')
            p_end = first_payroll.get('period_end_date')
            if p_start and p_end:
                approval_result = self.supabase.table('payroll_approvals').select('*').eq(
                    'period_start_date', p_start
                ).eq(
                    'period_end_date', p_end
                ).execute()
                if approval_result.data and len(approval_result.data) > 0:
                    ap = approval_result.data[0]
                    approval_data = {
                        "approved_by_accounting": ap.get('approved_by_accounting', False),
                        "approved_by_ceo": ap.get('approved_by_ceo', False),
                        "accounting_approved_at": ap.get('accounting_approved_at'),
                        "ceo_approved_at": ap.get('ceo_approved_at'),
                    }

            # STEP 2: Create archive report WITH approval status
            archive_report = {
                "archive_report_date": archive_date,
                "created_at": datetime.now().isoformat(),
                **approval_data
            }

            archive_result = self.supabase.table('archive_reports').insert(archive_report).execute()

            if not archive_result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create archive report"
                )

            archive_report_id = archive_result.data[0]['archive_report_id']

            # STEP 3: Prepare archive payroll entries
            archive_payrolls = []
            for payroll in payrolls.data:
                emp = payroll.get('employees', {})

                archive_payroll = {
                    "archive_report_id": archive_report_id,
                    "employee_id": payroll.get('employee_id'),
                    "days_worked": payroll.get('days_worked'),
                    "ot_hours": payroll.get('ot_hours'),
                    "no_of_absents": payroll.get('no_of_absents'),
                    "hours_worked": payroll.get('hours_worked'),
                    "tardiness_per_minute": payroll.get('tardiness_per_minute'),
                    "tardiness_deduction": payroll.get('tardiness_deduction'),
                    "absent_deduction": payroll.get('absent_deduction'),
                    "period_start_date": payroll.get('period_start_date'),
                    "period_end_date": payroll.get('period_end_date'),
                    "other_deductions": payroll.get('other_deductions'),
                    "total_deduction": payroll.get('total_deduction'),
                    "gross_pay": payroll.get('gross_pay'),
                    "net_pay": payroll.get('net_pay'),
                    "working_days": payroll.get('working_days'),
                    "salary_rate": payroll.get('salary_rate'),
                    "salary": payroll.get('salary'),
                    "pay_status": payroll.get('pay_status'),
                    "made_by": username,
                    "created_at": payroll.get('created_at'),
                    "employee_name_ln": emp.get('employee_name_ln'),
                    "employee_name_fn": emp.get('employee_name_fn'),
                    "employee_name_mi": emp.get('employee_name_mi'),
                    "employee_suffix": emp.get('employee_suffix'),
                    "employee_position": emp.get('employee_position'),
                    "sss_deduction": emp.get('sss_deduction'),
                    "phic_deduction": emp.get('phic_deduction'),
                    "pagibig_deduction": emp.get('pagibig_deduction'),
                    "basic_pay": emp.get('basic_pay')
                }

                archive_payrolls.append(archive_payroll)

            # STEP 4: Insert archived payrolls
            insert_result = self.supabase.table('archive_payrolls').insert(archive_payrolls).execute()

            if not insert_result.data:
                # Rollback: delete the archive report
                self.supabase.table('archive_reports').delete().eq('archive_report_id', archive_report_id).execute()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to archive payrolls"
                )

            # STEP 5: Delete all payrolls
            self.supabase.table('payrolls').delete().neq('payroll_id', 0).execute()  # Delete all

            # STEP 6: Clean up the payroll_approvals record for this period
            if p_start and p_end:
                try:
                    self.supabase.table('payroll_approvals').delete().eq(
                        'period_start_date', p_start
                    ).eq(
                        'period_end_date', p_end
                    ).execute()
                except Exception:
                    pass  # Non-critical, don't fail the archive

            return {
                "message": "Payrolls archived successfully",
                "archive_report_id": archive_report_id,
                "archive_report_date": archive_date,
                "payrolls_archived": len(archive_payrolls),
                "archived_by": username
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to archive payrolls: {str(e)}"
            )

    async def approve_archive(self, archive_report_id: int, approver_role: str, username: str):
        """Approve an archive report by accounting or CEO"""
        try:
            # Check if archive exists
            archive = self.supabase.table('archive_reports').select('*').eq('archive_report_id',
                                                                            archive_report_id).execute()

            if not archive.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Archive report {archive_report_id} not found"
                )

            current = archive.data[0]
            update_data = {}

            if approver_role == "accounting":
                if current.get('approved_by_accounting'):
                    return {"message": "Already approved by accounting", "already_approved": True}
                update_data = {
                    "approved_by_accounting": True,
                    "accounting_approved_at": datetime.now().isoformat()
                }
            elif approver_role == "ceo":
                if current.get('approved_by_ceo'):
                    return {"message": "Already approved by CEO", "already_approved": True}
                update_data = {
                    "approved_by_ceo": True,
                    "ceo_approved_at": datetime.now().isoformat()
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="approver_role must be 'accounting' or 'ceo'"
                )

            result = self.supabase.table('archive_reports').update(update_data).eq('archive_report_id',
                                                                                   archive_report_id).execute()

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update approval status"
                )

            return {
                "message": f"Archive approved by {approver_role}",
                "archive_report_id": archive_report_id,
                "approver_role": approver_role,
                "approved_by": username
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to approve archive: {str(e)}"
            )

    async def get_all_archives(self):
        """Get all archive reports with count of payrolls"""
        try:
            archives = self.supabase.table('archive_reports').select('*').order('created_at', desc=True).execute()

            result = []
            for archive in archives.data:
                # Count payrolls in this archive
                count = self.supabase.table('archive_payrolls').select('archive_payroll_id', count='exact').eq(
                    'archive_report_id', archive['archive_report_id']).execute()

                archive['total_payrolls_archived'] = count.count if count.count else 0
                result.append(archive)

            return {
                "archives": result,
                "total": len(result)
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archives: {str(e)}"
            )

    async def get_archive_by_id(self, archive_report_id: int):
        """Get specific archive with all payrolls"""
        try:
            # Get archive report
            archive = self.supabase.table('archive_reports').select('*').eq('archive_report_id',
                                                                            archive_report_id).execute()

            if not archive.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Archive report {archive_report_id} not found"
                )

            # Get all payrolls in this archive
            payrolls = self.supabase.table('archive_payrolls').select('*').eq('archive_report_id',
                                                                              archive_report_id).execute()

            return {
                "archive_report": archive.data[0],
                "payrolls": payrolls.data or [],
                "total_payrolls": len(payrolls.data) if payrolls.data else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive: {str(e)}"
            )

    async def delete_archive(self, archive_report_id: int):
        """Delete an archive report and all its payrolls (CASCADE)"""
        try:
            # Check if exists
            archive = self.supabase.table('archive_reports').select('archive_report_id').eq('archive_report_id',
                                                                                            archive_report_id).execute()

            if not archive.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Archive report {archive_report_id} not found"
                )

            # Delete (will cascade to archive_payrolls)
            self.supabase.table('archive_reports').delete().eq('archive_report_id', archive_report_id).execute()

            return {
                "message": f"Archive report {archive_report_id} deleted successfully"
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete archive: {str(e)}"
            )