"""Define validated identity requests and safe response shapes."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    """Accept bounded local credentials."""
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    """Expose only non-secret identity fields."""
    id: str
    name: str
    email: str
    role: str
    portfolioAccess: list[str]
    defaultLandingPage: Literal["dashboard", "applications"] | None
    mustChangePassword: bool
    effectivePermissions: list[str] = Field(default_factory=list)


class LoginResponse(BaseModel):
    """Return the bearer token and safe identity."""
    token: str
    user: UserResponse


class ProfileUpdate(BaseModel):
    """Accept a supported landing preference."""
    model_config = ConfigDict(extra="forbid")
    defaultLandingPage: Literal["dashboard", "applications"] | None


class PasswordUpdate(BaseModel):
    """Accept current credentials and a replacement password."""
    model_config = ConfigDict(extra="forbid")
    currentPassword: str = Field(min_length=1, max_length=1024)
    newPassword: str = Field(min_length=12, max_length=72)

    @field_validator("newPassword")
    @classmethod
    def check_bytes(cls, value: str) -> str:
        """Prevent bcrypt's byte limit from silently truncating input."""
        if len(value.encode()) > 72 or "\x00" in value:
            raise ValueError("Password must contain no null characters and be at most 72 UTF-8 bytes")
        return value
