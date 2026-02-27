from app.core.supabase_client import get_supabase
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
        self.supabase = get_supabase()
        self.otp_service = OTPService()

    # ─────────────────────────────────────────────
    # Brute Force Protection Helpers
    # ─────────────────────────────────────────────
    def _get_attempts(self, username: str):
        """Get current login attempt record for username"""
        result = self.supabase.table('login_attempts').select('*').eq('username', username).execute()
        return result.data[0] if result.data else None

    def _check_cooldown(self, username: str):
        """Raise 429 if user is still in cooldown period"""
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
                # Cooldown expired — reset
                self._reset_attempts(username)

    def _record_failed_attempt(self, username: str):
        """Increment failed attempts, lock if >= MAX_ATTEMPTS"""
        record = self._get_attempts(username)

        if not record:
            # First failed attempt
            self.supabase.table('login_attempts').insert({
                "username": username,
                "failed_attempts": 1,
                "locked_until": None,
                "last_attempt": datetime.now(UTC).isoformat()
            }).execute()
            return

        new_count = record['failed_attempts'] + 1
        locked_until = None

        if new_count >= MAX_ATTEMPTS:
            locked_until = (datetime.now(UTC) + timedelta(minutes=COOLDOWN_MINUTES)).isoformat()

        self.supabase.table('login_attempts').update({
            "failed_attempts": new_count,
            "locked_until": locked_until,
            "last_attempt": datetime.now(UTC).isoformat()
        }).eq('username', username).execute()

    def _reset_attempts(self, username: str):
        """Reset failed attempts after successful login or cooldown expiry"""
        self.supabase.table('login_attempts').update({
            "failed_attempts": 0,
            "locked_until": None,
            "last_attempt": datetime.now(UTC).isoformat()
        }).eq('username', username).execute()

    # ─────────────────────────────────────────────
    # EXISTING: Original endpoints (backward compat)
    # ─────────────────────────────────────────────
    async def register_user(self, user_data: UserRegister):
        try:
            valid_roles = ["admin", "super_admin", "accounting", "field"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}")

            existing_user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            if existing_user.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

            result = self.supabase.table('users').insert({
                "username": user_data.username,
                "user_password": hash_password(user_data.user_password),
                "user_role": user_data.user_role
            }).execute()

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def login_user(self, user_data: UserLogin):
        try:
            user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
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

    # ─────────────────────────────────────────────
    # OTP Register Flow
    # ─────────────────────────────────────────────
    async def send_register_otp(self, phone_number: str):
        try:
            existing = self.supabase.table('users').select('user_id').eq('phone_number', phone_number).execute()
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

            existing_user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            if existing_user.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

            result = self.supabase.table('users').insert({
                "username": user_data.username,
                "user_password": hash_password(user_data.user_password),
                "user_role": user_data.user_role,
                "phone_number": user_data.phone_number
            }).execute()

            if not result.data:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # OTP Login Flow (with Brute Force Protection)
    # ─────────────────────────────────────────────
    async def send_login_otp(self, username: str, user_password: str):
        """
        Step 1 - Login: Validate credentials then send OTP
        - 4 failed attempts = 5 minute cooldown
        - Phone number kukunin from DB automatically
        """
        try:
            # Check cooldown FIRST before anything else
            self._check_cooldown(username)

            user = self.supabase.table('users').select('*').eq('username', username).execute()
            if not user.data:
                # Still record attempt even if user doesn't exist (para hindi malaman ng attacker)
                self._record_failed_attempt(username)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            user_record = user.data[0]

            if user_record['user_role'] not in ("admin", "super_admin", "accounting", "field"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admin access required.")

            if not verify_password(user_password, user_record['user_password']):
                self._record_failed_attempt(username)
                # Check kung naka-lock na ngayon after recording
                self._check_cooldown(username)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            phone_number = user_record.get('phone_number')
            if not phone_number:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No phone number registered. Please contact admin.")

            # Success — reset failed attempts
            self._reset_attempts(username)

            await self.otp_service.send_otp(phone_number, purpose="login")

            masked = phone_number[:4] + "****" + phone_number[-3:]
            return {"message": f"OTP sent to {masked}. Please check your phone.", "phone_number": masked}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def verify_login_otp(self, user_data: OTPVerifyLogin):
        """
        Step 2 - Login: Verify OTP then return tokens
        - Also protected by brute force check
        """
        try:
            # Check cooldown
            self._check_cooldown(user_data.username)

            user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
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

            # Success — reset attempts
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