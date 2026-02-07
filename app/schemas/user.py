from pydantic import BaseModel
from typing import Optional


class UserInfo(BaseModel):
    user_id: int
    username: str
    user_role: str


class UserMeResponse(BaseModel):
    user_id: int
    username: str
    user_role: str
    message: str = "Current authenticated user"