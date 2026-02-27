from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import verify_access_token
from app.schemas.auth import TokenData

security = HTTPBearer()


async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Allow both admin and super_admin"""
    token = credentials.credentials
    payload = verify_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_role = payload.get("user_role")
    if user_role not in ("admin", "super_admin", "accounting", "field"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return TokenData(
        username=payload.get("sub"),
        user_id=payload.get("user_id"),
        user_role=user_role
    )


async def get_current_super_admin(current_admin: TokenData = Depends(get_current_admin)) -> TokenData:
    """Super admin only"""
    if current_admin.user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required"
        )
    return current_admin