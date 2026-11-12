"""Pydantic v2 request and response schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateUserRequest(BaseModel):
    """Schema for user registration requests. Role cannot be elevated by caller."""

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=72)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class UserResponse(BaseModel):
    """Public user representation excluding sensitive fields such as password hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    first_name: str
    last_name: str
    is_active: bool
    role: str


class UserStatusUpdateRequest(BaseModel):
    """Admin payload for updating a user's active status."""

    is_active: bool


class Token(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str


class TodoRequest(BaseModel):
    """Schema for creating or updating a todo item."""

    title: str = Field(min_length=3, max_length=100)
    description: str = Field(min_length=3, max_length=300)
    priority: int = Field(ge=1, le=5)
    complete: bool = False


class TodoResponse(BaseModel):
    """Serialized todo item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    priority: int
    complete: bool
    owner_id: int


class AdminStatsResponse(BaseModel):
    """Platform-wide statistics visible exclusively to administrators."""

    total_users: int
    active_users: int
    inactive_users: int
    total_todos: int
    completed_todos: int
    pending_todos: int
    message: Optional[str] = None

