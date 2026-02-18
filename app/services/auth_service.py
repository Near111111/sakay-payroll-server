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
    # EXISTING: Original endpoints (backward compat)
    # ─────────────────────────────────────────────
    async def register_user(self, user_data: UserRegister):
        try:
            valid_roles = ["admin", "super_admin"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}")
            
            existing_user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            if existing_user.data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
            
            hashed_password = hash_password(user_data.user_password)
            result = self.supabase.table('users').insert({
                "username": user_data.username,
                "user_password": hashed_password,
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
            
            if user_record['user_role'] not in ("admin", "super_admin"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admin access required.")
            
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
            
            if payload.get("user_role") not in ("admin", "super_admin"):
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
        """Step 1 - Register: Validate phone not taken, send OTP"""
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
        """Step 2 - Register: Verify OTP then create user"""
        try:
            await self.otp_service.verify_otp(
                phone_number=user_data.phone_number,
                otp_code=user_data.otp_code,
                purpose="register"
            )

            valid_roles = ["admin", "super_admin"]
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
    # OTP Login Flow
    # ─────────────────────────────────────────────
    async def send_login_otp(self, username: str, user_password: str):
        """
        Step 1 - Login: Validate credentials, get phone number from DB, send OTP
        Hindi na kailangan ng phone_number sa request — kukunin from DB
        """
        try:
            user = self.supabase.table('users').select('*').eq('username', username).execute()
            if not user.data:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            user_record = user.data[0]

            if user_record['user_role'] not in ("admin", "super_admin"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Admin access required.")

            if not verify_password(user_password, user_record['user_password']):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            # Kukunin ang phone number from DB — hindi na kailangan i-input ng user
            phone_number = user_record.get('phone_number')
            if not phone_number:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No phone number registered for this account. Please contact admin.")

            await self.otp_service.send_otp(phone_number, purpose="login")

            # I-mask ang phone number para sa security (e.g. 09562601594 → 0956****594)
            masked = phone_number[:4] + "****" + phone_number[-3:]
            return {"message": f"OTP sent to {masked}. Please check your phone.", "phone_number": masked}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    async def verify_login_otp(self, user_data: OTPVerifyLogin):
        """
        Step 2 - Login: Verify OTP then return tokens
        Kukunin ang phone number from DB gamit ang username
        """
        try:
            # Kunin ang user + phone number from DB
            user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            if not user.data:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            user_record = user.data[0]

            if not verify_password(user_data.user_password, user_record['user_password']):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

            phone_number = user_record.get('phone_number')
            if not phone_number:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No phone number registered for this account.")

            # Verify OTP gamit ang phone number from DB
            await self.otp_service.verify_otp(
                phone_number=phone_number,
                otp_code=user_data.otp_code,
                purpose="login"
            )

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