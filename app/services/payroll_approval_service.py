from app.core.db_client import db_fetch_one, db_execute
from fastapi import HTTPException, status
from datetime import datetime


class PayrollApprovalService:
    def __init__(self):
        pass

    async def get_approval(self, period_start: str, period_end: str):
        try:
            result = db_fetch_one(
                """
                SELECT * FROM payroll_approvals
                WHERE period_start_date = :period_start AND period_end_date = :period_end
                """,
                {"period_start": period_start, "period_end": period_end}
            )

            if result.data:
                return {"approval": result.data[0], "found": True}

            return {
                "approval": {
                    "period_start_date": period_start,
                    "period_end_date": period_end,
                    "approved_by_accounting": False,
                    "approved_by_ceo": False,
                    "accounting_approved_at": None,
                    "ceo_approved_at": None,
                },
                "found": False
            }
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get approval: {str(e)}")

    async def approve(self, period_start: str, period_end: str, approver_role: str, username: str):
        try:
            if approver_role not in ("accounting", "ceo"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approver_role must be 'accounting' or 'ceo'")

            existing = db_fetch_one(
                """
                SELECT * FROM payroll_approvals
                WHERE period_start_date = :period_start AND period_end_date = :period_end
                """,
                {"period_start": period_start, "period_end": period_end}
            )

            now = datetime.now().isoformat()

            if existing.data:
                record = existing.data[0]

                if approver_role == "accounting" and record.get('approved_by_accounting'):
                    return {"message": "Already approved by accounting", "already_approved": True}
                if approver_role == "ceo" and record.get('approved_by_ceo'):
                    return {"message": "Already approved by CEO", "already_approved": True}

                if approver_role == "accounting":
                    result = db_execute(
                        """
                        UPDATE payroll_approvals
                        SET approved_by_accounting = TRUE, accounting_approved_at = :now
                        WHERE approval_id = :approval_id RETURNING *
                        """,
                        {"now": now, "approval_id": record['approval_id']}
                    )
                else:
                    result = db_execute(
                        """
                        UPDATE payroll_approvals
                        SET approved_by_ceo = TRUE, ceo_approved_at = :now
                        WHERE approval_id = :approval_id RETURNING *
                        """,
                        {"now": now, "approval_id": record['approval_id']}
                    )
            else:
                result = db_execute(
                    """
                    INSERT INTO payroll_approvals (
                        period_start_date, period_end_date,
                        approved_by_accounting, approved_by_ceo,
                        accounting_approved_at, ceo_approved_at
                    ) VALUES (
                        :period_start, :period_end,
                        :approved_by_accounting, :approved_by_ceo,
                        :accounting_approved_at, :ceo_approved_at
                    ) RETURNING *
                    """,
                    {
                        "period_start": period_start,
                        "period_end": period_end,
                        "approved_by_accounting": approver_role == "accounting",
                        "approved_by_ceo": approver_role == "ceo",
                        "accounting_approved_at": now if approver_role == "accounting" else None,
                        "ceo_approved_at": now if approver_role == "ceo" else None,
                    }
                )

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save approval")

            return {
                "message": f"Approved by {approver_role}",
                "approver_role": approver_role,
                "approved_by": username,
                "approval": result.data[0]
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to approve: {str(e)}")