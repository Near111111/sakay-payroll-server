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


class AuthService:
    def __init__(self):
        self.supabase = get_supabase()
        self.otp_service = OTPService()
    
    # ─────────────────────────────────────────────
    # EXISTING: Original register (kept for backward compat)
    # ─────────────────────────────────────────────
    async def register_user(self, user_data: UserRegister):
        """Register a new admin or super_admin user (original, no OTP)"""
        try:
            valid_roles = ["admin", "super_admin"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}"
                )
            
            existing_user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            if existing_user.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists"
                )
            
            hashed_password = hash_password(user_data.user_password)
            new_user = {
                "username": user_data.username,
                "user_password": hashed_password,
                "user_role": user_data.user_role
            }
            
            result = self.supabase.table('users').insert(new_user).execute()
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user"
                )
            
            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # EXISTING: Original login (kept for backward compat)
    # ─────────────────────────────────────────────
    async def login_user(self, user_data: UserLogin):
        """Login admin or super_admin user and return tokens (original, no OTP)"""
        try:
            user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            user_record = user.data[0]
            
            if user_record['user_role'] not in ("admin", "super_admin"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Admin access required."
                )
            
            if not verify_password(user_data.user_password, user_record['user_password']):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            token_data = {
                "sub": user_record['username'],
                "user_id": user_record['user_id'],
                "user_role": user_record['user_role']
            }
            
            access_token = create_access_token(data=token_data)
            refresh_token = create_refresh_token(data=token_data)
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
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

    # ─────────────────────────────────────────────
    # EXISTING: Refresh token (unchanged)
    # ─────────────────────────────────────────────
    async def refresh_access_token(self, token_data: TokenRefresh):
        """Refresh access token using refresh token"""
        try:
            payload = verify_refresh_token(token_data.refresh_token)
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            if payload.get("user_role") not in ("admin", "super_admin"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            
            new_token_data = {
                "sub": payload.get("sub"),
                "user_id": payload.get("user_id"),
                "user_role": payload.get("user_role")
            }
            
            access_token = create_access_token(data=new_token_data)
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # NEW: OTP Register Flow
    # ─────────────────────────────────────────────
    async def send_register_otp(self, phone_number: str):
        """
        Step 1 - Register: Validate phone is not taken, then send OTP
        """
        try:
            # Check if phone already registered
            existing = self.supabase.table('users').select('user_id').eq(
                'phone_number', phone_number
            ).execute()
            
            if existing.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Phone number already registered"
                )
            
            await self.otp_service.send_otp(phone_number, purpose="register")
            
            return {
                "message": "OTP sent successfully. Please check your phone.",
                "phone_number": phone_number
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def verify_register_otp(self, user_data: OTPVerifyRegister):
        """
        Step 2 - Register: Verify OTP then create user
        """
        try:
            # Verify OTP first
            await self.otp_service.verify_otp(
                phone_number=user_data.phone_number,
                otp_code=user_data.otp_code,
                purpose="register"
            )

            # Validate role
            valid_roles = ["admin", "super_admin"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}"
                )

            # Check if username already exists
            existing_user = self.supabase.table('users').select('*').eq(
                'username', user_data.username
            ).execute()
            if existing_user.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists"
                )

            # Create user
            hashed_password = hash_password(user_data.user_password)
            new_user = {
                "username": user_data.username,
                "user_password": hashed_password,
                "user_role": user_data.user_role,
                "phone_number": user_data.phone_number
            }

            result = self.supabase.table('users').insert(new_user).execute()
            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create user"
                )

            return result.data[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # ─────────────────────────────────────────────
    # NEW: OTP Login Flow
    # ─────────────────────────────────────────────
    async def send_login_otp(self, username: str, user_password: str, phone_number: str):
        """
        Step 1 - Login: Validate credentials + phone match, then send OTP
        """
        try:
            # Find user
            user = self.supabase.table('users').select('*').eq('username', username).execute()
            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )

            user_record = user.data[0]

            # Check role
            if user_record['user_role'] not in ("admin", "super_admin"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Admin access required."
                )

            # Verify password
            if not verify_password(user_password, user_record['user_password']):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )

            # Verify phone matches
            if user_record.get('phone_number') != phone_number:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Phone number does not match registered number"
                )

            await self.otp_service.send_otp(phone_number, purpose="login")

            return {
                "message": "OTP sent successfully. Please check your phone.",
                "phone_number": phone_number
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def verify_login_otp(self, user_data: OTPVerifyLogin):
        """
        Step 2 - Login: Verify OTP then return tokens
        """
        try:
            # Verify OTP first
            await self.otp_service.verify_otp(
                phone_number=user_data.phone_number,
                otp_code=user_data.otp_code,
                purpose="login"
            )

            # Re-fetch user to build tokens
            user = self.supabase.table('users').select('*').eq(
                'username', user_data.username
            ).execute()
            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )

            user_record = user.data[0]

            # Verify password again (security double-check)
            if not verify_password(user_data.user_password, user_record['user_password']):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )

            token_data = {
                "sub": user_record['username'],
                "user_id": user_record['user_id'],
                "user_role": user_record['user_role']
            }

            access_token = create_access_token(data=token_data)
            refresh_token = create_refresh_token(data=token_data)

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
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