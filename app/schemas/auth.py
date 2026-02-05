from pydantic import BaseModel, field_validator
from typing import Optional


class UserRegister(BaseModel):
    username: str
    user_password: str
    user_role: str = "admin"  # Default to admin
    
    @field_validator('username')
    def username_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        return v
    
    @field_validator('user_password')
    def password_strength(cls, v):
        if len(v) < 8:  # Stronger requirement for admin
            raise ValueError('Password must be at least 8 characters')
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