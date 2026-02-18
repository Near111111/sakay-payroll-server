from pydantic import BaseModel, field_validator
from typing import Optional


class UserRegister(BaseModel):
    username: str
    user_password: str
    user_role: str = "admin"
    
    @field_validator('username')
    def username_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        return v
    
    @field_validator('user_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v
    
    @field_validator('user_role')
    def validate_user_role(cls, v):
        valid_roles = ["admin", "super_admin"]
        if v not in valid_roles:
            raise ValueError(f'User role must be one of: {valid_roles}')
        return v


class UserLogin(BaseModel):
    username: str
    user_password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    user_role: Optional[str] = None


class UserResponse(BaseModel):
    user_id: int
    username: str
    user_role: str


# ─────────────────────────────────────────────
# NEW: OTP Schemas
# ─────────────────────────────────────────────

class OTPRequest(BaseModel):
    """Step 1 - Register: Just the phone number"""
    phone_number: str

    @field_validator('phone_number')
    def validate_phone(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Phone number cannot be empty')
        return v


class OTPVerifyRegister(BaseModel):
    """Step 2 - Register: Full user data + OTP code"""
    username: str
    user_password: str
    user_role: str = "admin"
    phone_number: str
    otp_code: str

    @field_validator('username')
    def username_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        return v

    @field_validator('user_password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

    @field_validator('user_role')
    def validate_user_role(cls, v):
        valid_roles = ["admin", "super_admin"]
        if v not in valid_roles:
            raise ValueError(f'User role must be one of: {valid_roles}')
        return v

    @field_validator('otp_code')
    def validate_otp_code(cls, v):
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError('OTP must be a 6-digit number')
        return v


class OTPVerifyLogin(BaseModel):
    """Step 2 - Login: Credentials + OTP code"""
    username: str
    user_password: str
    phone_number: str
    otp_code: str

    @field_validator('otp_code')
    def validate_otp_code(cls, v):
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError('OTP must be a 6-digit number')
        return v


class LoginOTPRequest(BaseModel):
    """Step 1 - Login: Credentials + phone number"""
    username: str
    user_password: str
    phone_number: str


class OTPSentResponse(BaseModel):
    """Response after sending OTP"""
    message: str
    phone_number: str