from fastapi import APIRouter, HTTPException, Depends, Request
from app.schemas.auth import (
    UserRegister,
    UserResponse,
    UserLogin,
    TokenResponse,
    TokenRefresh,
    TokenData,
    OTPRequest,
    OTPVerifyRegister,
    OTPVerifyLogin,
    LoginOTPRequest,
    OTPSentResponse
)
from app.services.auth_service import AuthService
from app.core.dependencies import get_current_admin
from app.core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_service = AuthService()


# ─────────────────────────────────────────────
# EXISTING: Original endpoints (backward compat)
# ─────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, user: UserRegister):
    """Register a new ADMIN user (original - no OTP)"""
    new_user = await auth_service.register_user(user)
    return {"user_id": new_user["user_id"], "username": new_user["username"], "user_role": new_user["user_role"]}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, user: UserLogin):
    """Admin login (original - no OTP)"""
    return await auth_service.login_user(user)


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request, token_data: TokenRefresh):
    """Refresh access token using refresh token"""
    return await auth_service.refresh_access_token(token_data)


@router.post("/logout")
@limiter.limit("20/minute")
async def logout(request: Request, current_admin: TokenData = Depends(get_current_admin)):
    """Logout current user"""
    return {
        "message": f"User {current_admin.username} logged out successfully",
        "user_id": current_admin.user_id,
        "username": current_admin.username
    }


# ─────────────────────────────────────────────
# OTP Register Flow
# ─────────────────────────────────────────────

@router.post("/register/send-otp", response_model=OTPSentResponse)
@limiter.limit("5/minute")
async def register_send_otp(request: Request, data: OTPRequest):
    """
    Step 1 - Register: Send OTP to phone number

    - I-input ang phone number ng bagong user
    - Mag-se-send ng OTP sa phone
    - OTP expires in 5 minutes
    """
    return await auth_service.send_register_otp(data.phone_number)


@router.post("/register/verify-otp", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register_verify_otp(request: Request, data: OTPVerifyRegister):
    """
    Step 2 - Register: Verify OTP and create user

    - I-input ang username, password, role, phone number, at OTP
    - Gagawa ng user account na may phone number
    """
    new_user = await auth_service.verify_register_otp(data)
    return {"user_id": new_user["user_id"], "username": new_user["username"], "user_role": new_user["user_role"]}


# ─────────────────────────────────────────────
# OTP Login Flow
# ─────────────────────────────────────────────

@router.post("/login/send-otp", response_model=OTPSentResponse)
@limiter.limit("5/minute")
async def login_send_otp(request: Request, data: LoginOTPRequest):
    """
    Step 1 - Login: Validate credentials then send OTP

    - I-input lang ang username at password
    - Automatic na kukunin ang phone number from database
    - OTP ipapadala sa registered phone number ng user
    - Phone number ay masked sa response (e.g. 0956****594)
    """
    return await auth_service.send_login_otp(
        username=data.username,
        user_password=data.user_password
    )


@router.post("/login/verify-otp", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login_verify_otp(request: Request, data: OTPVerifyLogin):
    """
    Step 2 - Login: Verify OTP and return tokens

    - I-input ang username, password, at OTP code lang
    - Hindi na kailangan ng phone number — automatic na kukunin from DB
    - Mag-re-return ng access_token + refresh_token
    """
    return await auth_service.verify_login_otp(data)


# ─────────────────────────────────────────────
# Forgot Password Flow
# ─────────────────────────────────────────────

from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordVerifyOTP,
    ForgotPasswordReset,
    ForgotPasswordVerifyResponse,
)


@router.post("/forgot-password/send-otp", response_model=OTPSentResponse)
@limiter.limit("5/minute")
async def forgot_password_send_otp(request: Request, data: ForgotPasswordRequest):
    """
    Step 1 - Forgot Password: I-input ang phone number.
    Mag-se-send ng OTP sa registered na phone number.
    """
    return await auth_service.forgot_password_send_otp(data.phone_number)


@router.post("/forgot-password/verify-otp", response_model=ForgotPasswordVerifyResponse)
@limiter.limit("5/minute")
async def forgot_password_verify_otp(request: Request, data: ForgotPasswordVerifyOTP):
    """
    Step 2 - Forgot Password: I-verify ang OTP.
    Mag-re-return ng reset_token (valid 10 minutes).
    """
    return await auth_service.forgot_password_verify_otp(data.phone_number, data.otp_code)


@router.post("/forgot-password/reset")
@limiter.limit("5/minute")
async def forgot_password_reset(request: Request, data: ForgotPasswordReset):
    """
    Step 3 - Forgot Password: I-reset ang password.
    Kailangan ng reset_token mula sa Step 2.
    """
    return await auth_service.forgot_password_reset(data.reset_token, data.new_password)