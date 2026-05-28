from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    full_name: str
    role: str = UserRole.OPERATOR.value


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserResponse(BaseModel):
    id: str
    org_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
