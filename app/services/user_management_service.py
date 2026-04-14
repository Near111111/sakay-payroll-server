from app.core.db_client import db_fetch_all, db_fetch_one, db_execute
from fastapi import HTTPException, status


class UserManagementService:

    def get_all_users(self):
        """Get all users with their status, excluding super admins"""
        try:
            result = db_fetch_all(
                """
                SELECT user_id, username, user_role, is_active
                FROM users
                WHERE user_role != 'super_admin'
                ORDER BY user_id ASC
                """
            )
            return result.data
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    def toggle_user_status(self, target_user_id: int, requesting_user_id: int, requesting_user_role: str):
        """Enable or disable a user account"""
        try:
            if requesting_user_role != "super_admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super admins can enable/disable user accounts."
                )

            if target_user_id == requesting_user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot disable your own account."
                )

            user_result = db_fetch_one(
                "SELECT user_id, username, user_role, is_active FROM users WHERE user_id = :user_id",
                {"user_id": target_user_id}
            )
            if not user_result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found."
                )

            user = user_result.data[0]

            if user["user_role"] == "super_admin":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot disable a super admin account."
                )

            new_status = not user["is_active"]

            db_execute(
                "UPDATE users SET is_active = :is_active WHERE user_id = :user_id",
                {"is_active": new_status, "user_id": target_user_id}
            )

            action = "enabled" if new_status else "disabled"
            return {
                "message": f"User '{user['username']}' has been {action} successfully.",
                "user_id": target_user_id,
                "username": user["username"],
                "is_active": new_status
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )