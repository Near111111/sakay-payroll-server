from app.core.db_client import db_fetch_all, db_fetch_one, db_execute
from app.schemas.archive import ArchiveReportCreate
from fastapi import HTTPException, status
from datetime import datetime


class ArchiveService:
    def __init__(self):
        pass

    async def create_archive(self, archive_date: str, user_id: int, username: str):
        try:
            # STEP 1: Get all payrolls with employee data via JOIN
            payrolls = db_fetch_all(
                """
                SELECT p.*,
                    e.employee_name_fn, e.employee_name_mi, e.employee_name_ln,
                    e.employee_suffix, e.employee_position,
                    e.sss_deduction, e.phic_deduction, e.pagibig_deduction, e.basic_pay
                FROM payrolls p
                JOIN employees e ON e.employee_id = p.employee_id
                """
            )

            if not payrolls.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No payrolls to archive")

            first_payroll = payrolls.data[0]
            p_start = first_payroll.get('period_start_date')
            p_end = first_payroll.get('period_end_date')

            approval_data = {}
            if p_start and p_end:
                try:
                    approval_result = db_fetch_one(
                        """
                        SELECT * FROM payroll_approvals
                        WHERE period_start_date = :p_start AND period_end_date = :p_end
                        """,
                        {"p_start": p_start, "p_end": p_end}
                    )
                    if approval_result.data:
                        ap = approval_result.data[0]
                        approval_data = {
                            "approved_by_accounting": ap.get('approved_by_accounting', False),
                            "approved_by_ceo": ap.get('approved_by_ceo', False),
                            "accounting_approved_at": ap.get('accounting_approved_at'),
                            "ceo_approved_at": ap.get('ceo_approved_at'),
                        }
                except Exception:
                    pass

            # STEP 2: Create archive report
            archive_result = db_execute(
                """
                INSERT INTO archive_reports (
                    archive_report_date, created_at,
                    approved_by_accounting, approved_by_ceo,
                    accounting_approved_at, ceo_approved_at
                ) VALUES (
                    :archive_report_date, :created_at,
                    :approved_by_accounting, :approved_by_ceo,
                    :accounting_approved_at, :ceo_approved_at
                ) RETURNING *
                """,
                {
                    "archive_report_date": archive_date,
                    "created_at": datetime.now().isoformat(),
                    "approved_by_accounting": approval_data.get("approved_by_accounting", False),
                    "approved_by_ceo": approval_data.get("approved_by_ceo", False),
                    "accounting_approved_at": approval_data.get("accounting_approved_at"),
                    "ceo_approved_at": approval_data.get("ceo_approved_at"),
                }
            )

            if not archive_result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create archive report")

            archive_report_id = archive_result.data[0]['archive_report_id']

            # STEP 3: Prepare and insert archive payrolls
            archive_payrolls = []
            for payroll in payrolls.data:
                archive_payrolls.append({
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
                    "employee_name_ln": payroll.get('employee_name_ln'),
                    "employee_name_fn": payroll.get('employee_name_fn'),
                    "employee_name_mi": payroll.get('employee_name_mi'),
                    "employee_suffix": payroll.get('employee_suffix'),
                    "employee_position": payroll.get('employee_position'),
                    "sss_deduction": payroll.get('sss_deduction'),
                    "phic_deduction": payroll.get('phic_deduction'),
                    "pagibig_deduction": payroll.get('pagibig_deduction'),
                    "basic_pay": payroll.get('basic_pay'),
                })

            # Insert one by one (SQLAlchemy text() doesn't support bulk insert easily)
            for ap in archive_payrolls:
                cols = ", ".join(ap.keys())
                vals = ", ".join([f":{k}" for k in ap.keys()])
                result = db_execute(f"INSERT INTO archive_payrolls ({cols}) VALUES ({vals}) RETURNING *", ap)
                if not result.data:
                    db_execute(
                        "DELETE FROM archive_reports WHERE archive_report_id = :id",
                        {"id": archive_report_id}
                    )
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to archive payrolls")

            # STEP 4: Delete all current payrolls
            db_execute("DELETE FROM payrolls WHERE payroll_id > 0")

            # STEP 5: Clean up payroll_approvals for this period
            if p_start and p_end:
                try:
                    db_execute(
                        "DELETE FROM payroll_approvals WHERE period_start_date = :p_start AND period_end_date = :p_end",
                        {"p_start": p_start, "p_end": p_end}
                    )
                except Exception:
                    pass

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
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to archive payrolls: {str(e)}")

    async def approve_archive(self, archive_report_id: int, approver_role: str, username: str):
        try:
            archive = db_fetch_one(
                "SELECT * FROM archive_reports WHERE archive_report_id = :id",
                {"id": archive_report_id}
            )

            if not archive.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Archive report {archive_report_id} not found")

            current = archive.data[0]
            now = datetime.now().isoformat()

            if approver_role == "accounting":
                if current.get('approved_by_accounting'):
                    return {"message": "Already approved by accounting", "already_approved": True}
                result = db_execute(
                    "UPDATE archive_reports SET approved_by_accounting = TRUE, accounting_approved_at = :now WHERE archive_report_id = :id RETURNING *",
                    {"now": now, "id": archive_report_id}
                )
            elif approver_role == "ceo":
                if current.get('approved_by_ceo'):
                    return {"message": "Already approved by CEO", "already_approved": True}
                result = db_execute(
                    "UPDATE archive_reports SET approved_by_ceo = TRUE, ceo_approved_at = :now WHERE archive_report_id = :id RETURNING *",
                    {"now": now, "id": archive_report_id}
                )
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approver_role must be 'accounting' or 'ceo'")

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update approval status")

            return {
                "message": f"Archive approved by {approver_role}",
                "archive_report_id": archive_report_id,
                "approver_role": approver_role,
                "approved_by": username
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to approve archive: {str(e)}")

    async def get_all_archives(self):
        try:
            archives = db_fetch_all("SELECT * FROM archive_reports ORDER BY created_at DESC")

            result = []
            for archive in archives.data:
                count = db_fetch_one(
                    "SELECT COUNT(*) as count FROM archive_payrolls WHERE archive_report_id = :id",
                    {"id": archive['archive_report_id']}
                )
                archive['total_payrolls_archived'] = count.data[0]['count'] if count.data else 0
                result.append(archive)

            return {"archives": result, "total": len(result)}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get archives: {str(e)}")

    async def get_archive_by_id(self, archive_report_id: int):
        try:
            archive = db_fetch_one(
                "SELECT * FROM archive_reports WHERE archive_report_id = :id",
                {"id": archive_report_id}
            )
            if not archive.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Archive report {archive_report_id} not found")

            payrolls = db_fetch_all(
                "SELECT * FROM archive_payrolls WHERE archive_report_id = :id",
                {"id": archive_report_id}
            )

            return {
                "archive_report": archive.data[0],
                "payrolls": payrolls.data or [],
                "total_payrolls": len(payrolls.data) if payrolls.data else 0
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get archive: {str(e)}")

    async def delete_archive(self, archive_report_id: int):
        try:
            archive = db_fetch_one(
                "SELECT archive_report_id FROM archive_reports WHERE archive_report_id = :id",
                {"id": archive_report_id}
            )
            if not archive.data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Archive report {archive_report_id} not found")

            db_execute(
                "DELETE FROM archive_reports WHERE archive_report_id = :id",
                {"id": archive_report_id}
            )

            return {"message": f"Archive report {archive_report_id} deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete archive: {str(e)}")