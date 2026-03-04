from app.core.supabase_client import get_supabase
from fastapi import HTTPException, status
from datetime import datetime


class PayrollApprovalService:
    def __init__(self):
        self.supabase = get_supabase()

    async def get_approval(self, period_start: str, period_end: str):
        """Get approval status for a specific period"""
        try:
            result = self.supabase.table('payroll_approvals').select('*').eq(
                'period_start_date', period_start
            ).eq(
                'period_end_date', period_end
            ).execute()

            if result.data and len(result.data) > 0:
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get approval: {str(e)}"
            )

    async def approve(self, period_start: str, period_end: str, approver_role: str, username: str):
        """Approve current period payroll by accounting or CEO"""
        try:
            if approver_role not in ("accounting", "ceo"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="approver_role must be 'accounting' or 'ceo'"
                )

            # Check if record exists
            existing = self.supabase.table('payroll_approvals').select('*').eq(
                'period_start_date', period_start
            ).eq(
                'period_end_date', period_end
            ).execute()

            now = datetime.now().isoformat()

            if existing.data and len(existing.data) > 0:
                record = existing.data[0]

                if approver_role == "accounting" and record.get('approved_by_accounting'):
                    return {"message": "Already approved by accounting", "already_approved": True}
                if approver_role == "ceo" and record.get('approved_by_ceo'):
                    return {"message": "Already approved by CEO", "already_approved": True}

                update_data = {}
                if approver_role == "accounting":
                    update_data = {"approved_by_accounting": True, "accounting_approved_at": now}
                else:
                    update_data = {"approved_by_ceo": True, "ceo_approved_at": now}

                result = self.supabase.table('payroll_approvals').update(update_data).eq(
                    'approval_id', record['approval_id']
                ).execute()
            else:
                # Create new record
                new_record = {
                    "period_start_date": period_start,
                    "period_end_date": period_end,
                    "approved_by_accounting": approver_role == "accounting",
                    "approved_by_ceo": approver_role == "ceo",
                    "accounting_approved_at": now if approver_role == "accounting" else None,
                    "ceo_approved_at": now if approver_role == "ceo" else None,
                }
                result = self.supabase.table('payroll_approvals').insert(new_record).execute()

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to save approval"
                )

            return {
                "message": f"Approved by {approver_role}",
                "approver_role": approver_role,
                "approved_by": username,
                "approval": result.data[0]
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to approve: {str(e)}"
            )