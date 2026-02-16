from app.core.supabase_client import get_supabase
from app.core.security import (
    hash_password, 
    verify_password, 
    create_access_token, 
    create_refresh_token,
    verify_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.schemas.auth import UserRegister, UserLogin, TokenRefresh
from fastapi import HTTPException, status


class AuthService:
    def __init__(self):
        self.supabase = get_supabase()
    
    async def register_user(self, user_data: UserRegister):
        """Register a new admin or super_admin user"""
        try:
            # Allow admin and super_admin roles
            valid_roles = ["admin", "super_admin"]
            if user_data.user_role not in valid_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User role must be one of: {valid_roles}"
                )
            
            # Check if username already exists
            existing_user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            
            if existing_user.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already exists"
                )
            
            # Hash the password
            hashed_password = hash_password(user_data.user_password)
            
            # Insert new user with specified role
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def login_user(self, user_data: UserLogin):
        """Login admin or super_admin user and return tokens"""
        try:
            # Find user by username
            user = self.supabase.table('users').select('*').eq('username', user_data.username).execute()
            
            if not user.data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            user_record = user.data[0]
            
            # Check if user is admin or super_admin
            if user_record['user_role'] not in ("admin", "super_admin"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. Admin access required."
                )
            
            # Verify password
            if not verify_password(user_data.user_password, user_record['user_password']):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Create token payload with actual user role
            token_data = {
                "sub": user_record['username'],
                "user_id": user_record['user_id'],
                "user_role": user_record['user_role']
            }
            
            # Create tokens
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
    
    async def refresh_access_token(self, token_data: TokenRefresh):
        """Refresh access token using refresh token"""
        try:
            # Verify refresh token
            payload = verify_refresh_token(token_data.refresh_token)
            
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired refresh token",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Verify it's an admin or super_admin
            if payload.get("user_role") not in ("admin", "super_admin"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            
            # Create new access token with actual user role
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )