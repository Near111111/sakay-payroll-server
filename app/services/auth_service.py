from app.core.db_client import db_fetch_one, db_execute
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.schemas.auth import UserRegister, UserLogin, TokenRefresh, OTPVerifyRegister, OTPVerifyLogin
from app.services.otp_service import OTPService
from fastapi import HTTPException, status
from datetime import datetime, timedelta
import pytz

UTC = pytz.utc
MAX_ATTEMPTS = 4
COOLDOWN_MINUTES = 5


class AuthService:
    def __init__(self):
        self.otp_service = OTPService()

    def _get_attempts(self, username: str):
        result = db_fetch_one(
            "SELECT * FROM login_attempts WHERE username = :username",
            {"username": username}
        )
        return result.data[0] if result.data else None

    def _check_cooldown(self, username: str):
        record = self._get_attempts(username)
        if not record:
            return
        if record.get('locked_until'):
            locked_until = datetime.fromisoformat(record['locked_until'].replace('Z', '+00:00'))
            now = datetime.now(UTC)
            if now < locked_until:
                remaining = int((locked_until - now).total_seconds() / 60) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed attempts. Please try again in {remaining} minute(s)."
                )
            else:
                self._reset_attempts(username)

    def _record_failed_attempt(self, username: str):
        record = self._get_attempts(username)
        if not record:
            db_execute(
                """
                INSERT INTO login_attempts (username, failed_attempts, locked_until, last_attempt)
                VALUES (:username, 1, NULL, :last_attempt)
                """,
                {"username": username, "last_attempt": datetime.now(UTC).isoformat()}
            )
            return

        new_count = record['failed_attempts'] + 1
        locked_until = None
        if new_count >= MAX_ATTEMPTS:
            locked_until = (datetime.now(UTC) + timedelta(minutes=COOLDOWN_MINUTES)).isoformat()

        db_execute(
            """
            UPDATE login_attempts
            SET failed_attempts = :count, locked_until = :locked_until, last_attempt = :last_attempt
            WHERE username = :username
            """,
            {
                "count": new_count,
                "locked_until": locked_until,
                "last_attempt": datetime.now(UTC).isoformat(),
                "username": username
            }
        )

    def _reset_attempts(self, username: str):
        db_execute(
            """
            UPDATE login_attempts
            SET failed_attempts = 0, locked_until = NULL, last_attempt = :last_attempt
            WHERE username = :username
            """,
            {"last_attempt": datetime.now(UTC).isoformat(), "username": username}
        )

    async def register_user(self, user_data: UserRegister):
        try:
            valid_roles = ["admin", "super_admin", "accounting", "field"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}")

            existing_user = db_fetch_one(
                "SELECT * FROM users WHERE username = :username",
                {"username": user_data.username}
            )
            if existing_user.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

            result = db_execute(
                """
                INSERT INTO users (username, user_password, user_role)
                VALUES (:username, :user_password, :user_role)
                RETURNING *
                """,
                {
                    "username": user_data.username,
                    "user_password": hash_password(user_data.user_password),
                    "user_role": user_data.user_role
                }
            )

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def login_user(self, user_data: UserLogin):
        try:
            user = db_fetch_one(
                "SELECT * FROM users WHERE username = :username",
                {"username": user_data.username}
            )
            if not user.data:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password", headers={"WWW-Authenticate": "Bearer"})

            user_record = user.data[0]

            if user_record['user_role'] not in ("admin", "super_admin", "accounting", "field"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

            if not verify_password(user_data.user_password, user_record['user_password']):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password", headers={"WWW-Authenticate": "Bearer"})

            token_data = {
                "sub": user_record['username'],
                "user_id": user_record['user_id'],
                "user_role": user_record['user_role']
            }

            return {
                "access_token": create_access_token(data=token_data),
                "refresh_token": create_refresh_token(data=token_data),
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": {
                    "user_id": user_record['user_id'],
                    "username": user_record['username'],
                    "user_role": user_record['user_role']
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def refresh_access_token(self, token_data: TokenRefresh):
        try:
            payload = verify_refresh_token(token_data.refresh_token)
            if not payload:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token", headers={"WWW-Authenticate": "Bearer"})

            if payload.get("user_role") not in ("admin", "super_admin", "accounting", "field"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

            new_token_data = {
                "sub": payload.get("sub"),
                "user_id": payload.get("user_id"),
                "user_role": payload.get("user_role")
            }

            return {
                "access_token": create_access_token(data=new_token_data),
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def send_register_otp(self, phone_number: str):
        try:
            existing = db_fetch_one(
                "SELECT user_id FROM users WHERE phone_number = :phone_number",
                {"phone_number": phone_number}
            )
            if existing.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number already registered")

            await self.otp_service.send_otp(phone_number, purpose="register")
            return {"message": "OTP sent successfully. Please check your phone.", "phone_number": phone_number}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def verify_register_otp(self, user_data: OTPVerifyRegister):
        try:
            await self.otp_service.verify_otp(
                phone_number=user_data.phone_number,
                otp_code=user_data.otp_code,
                purpose="register"
            )

            valid_roles = ["admin", "super_admin", "accounting", "field"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}")

            existing_user = db_fetch_one(
                "SELECT * FROM users WHERE username = :username",
                {"username": user_data.username}
            )
            if existing_user.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

            result = db_execute(
                """
                INSERT INTO users (username, user_password, user_role, phone_number)
                VALUES (:username, :user_password, :user_role, :phone_number)
                RETURNING *
                """,
                {
                    "username": user_data.username,
                    "user_password": hash_password(user_data.user_password),
                    "user_role": user_data.user_role,
                    "phone_number": user_data.phone_number
                }
            )

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def send_login_otp(self, username: str, user_password: str):
        try:
            self._check_cooldown(username)

            user = db_fetch_one(
                "SELECT * FROM users WHERE username = :username",
                {"username": username}
            )
            if not user.data:
                self._record_failed_attempt(username)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            user_record = user.data[0]

            if user_record['user_role'] not in ("admin", "super_admin", "accounting", "field"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admin access required.")

            if not verify_password(user_password, user_record['user_password']):
                self._record_failed_attempt(username)
                self._check_cooldown(username)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            phone_number = user_record.get('phone_number')
            if not phone_number:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No phone number registered. Please contact admin.")

            self._reset_attempts(username)
            await self.otp_service.send_otp(phone_number, purpose="login")

            masked = phone_number[:4] + "****" + phone_number[-3:]
            return {"message": f"OTP sent to {masked}. Please check your phone.", "phone_number": masked}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def verify_login_otp(self, user_data: OTPVerifyLogin):
        try:
            self._check_cooldown(user_data.username)

            user = db_fetch_one(
                "SELECT * FROM users WHERE username = :username",
                {"username": user_data.username}
            )
            if not user.data:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            user_record = user.data[0]

            if not verify_password(user_data.user_password, user_record['user_password']):
                self._record_failed_attempt(user_data.username)
                self._check_cooldown(user_data.username)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            phone_number = user_record.get('phone_number')
            if not phone_number:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No phone number registered for this account.")

            await self.otp_service.verify_otp(
                phone_number=phone_number,
                otp_code=user_data.otp_code,
                purpose="login"
            )

            self._reset_attempts(user_data.username)

            token_data = {
                "sub": user_record['username'],
                "user_id": user_record['user_id'],
                "user_role": user_record['user_role']
            }

            return {
                "access_token": create_access_token(data=token_data),
                "refresh_token": create_refresh_token(data=token_data),
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": {
                    "user_id": user_record['user_id'],
                    "username": user_record['username'],
                    "user_role": user_record['user_role']
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    # ─── Forgot Password: Step 1 — Send OTP to phone ─────────────────────────
    async def forgot_password_send_otp(self, phone_number: str):
        try:
            # Check if phone number exists in users table
            user = db_fetch_one(
                "SELECT * FROM users WHERE phone_number = :phone_number",
                {"phone_number": phone_number}
            )
            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No account found with this phone number."
                )

            await self.otp_service.send_otp(phone_number, purpose="forgot_password")

            masked = phone_number[:4] + "****" + phone_number[-3:]
            return {
                "message": f"OTP sent to {masked}. Please check your phone.",
                "phone_number": masked
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─── Forgot Password: Step 2 — Verify OTP, return reset token ────────────
    async def forgot_password_verify_otp(self, phone_number: str, otp_code: str):
        try:
            await self.otp_service.verify_otp(
                phone_number=phone_number,
                otp_code=otp_code,
                purpose="forgot_password"
            )

            # Generate a short-lived reset token (reuse JWT, 10 min expiry)
            reset_token = create_access_token(
                data={"sub": phone_number, "type_override": "reset"},
                expires_delta=timedelta(minutes=10)
            )

            return {
                "message": "OTP verified. You may now reset your password.",
                "reset_token": reset_token
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─── Forgot Password: Step 3 — Reset password using reset token ──────────
    async def forgot_password_reset(self, reset_token: str, new_password: str):
        try:
            from app.core.security import verify_access_token
            payload = verify_access_token(reset_token)

            if not payload or payload.get("type_override") != "reset":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired reset token."
                )

            phone_number = payload.get("sub")

            user = db_fetch_one(
                "SELECT * FROM users WHERE phone_number = :phone_number",
                {"phone_number": phone_number}
            )
            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found."
                )

            db_execute(
                "UPDATE users SET user_password = :user_password WHERE phone_number = :phone_number",
                {
                    "user_password": hash_password(new_password),
                    "phone_number": phone_number
                }
            )

            return {"message": "Password reset successfully. You may now log in."}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))