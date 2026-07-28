from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def reject_email_as_password(self) -> Self:
        if self.email.lower() in self.password.lower():
            raise ValueError("password must not contain the email address")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
