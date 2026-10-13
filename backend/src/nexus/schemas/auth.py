from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[\w.@+-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "session"
    user_id: int
    email: str
    csrf_token: str
    expires_at: datetime | None = None


class SessionInfo(BaseModel):
    id: int
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_seen_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    current: bool = False


class MeResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    preferences: dict[str, Any] = Field(default_factory=dict)
    session: SessionInfo | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class SessionCookie(BaseModel):
    key: str
    value: str
    httponly: bool
    secure: bool
    samesite: str
    max_age: int
    path: str
