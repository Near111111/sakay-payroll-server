from pydantic import BaseModel
from typing import List


class UserListItem(BaseModel):
    user_id: int
    username: str
    user_role: str
    is_active: bool


class UserListResponse(BaseModel):
    users: List[UserListItem]
    total: int


class ToggleUserStatusResponse(BaseModel):
    message: str
    user_id: int
    username: str
    is_active: bool