"""Validate administration requests and response documents."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

RoleName = Literal['Administrator', 'Executive', 'Portfolio Leader', 'Engineer', 'Auditor', 'Read Only']
Permission = Literal['view', 'create', 'edit', 'delete', 'export', 'administer']


class UserInput(BaseModel):
    """Accept account attributes managed by an administrator."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    role: RoleName
    portfolioAccess: list[str] = Field(default_factory=list, max_length=100)
    status: Literal['Active', 'Inactive'] = 'Active'
    managerName: str | None = Field(default=None, max_length=200)
    vendorIndicator: bool = False
    defaultLandingPage: Literal['dashboard', 'applications'] | None = None

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize emails consistently with sign-in."""
        return value.lower()

    @field_validator('portfolioAccess')
    @classmethod
    def unique_access(cls, value: list[str]) -> list[str]:
        """Reject repeated portfolio assignments."""
        if len(value) != len(set(value)):
            raise ValueError('Duplicate portfolio assignment')
        return value


class UserCreate(UserInput):
    """Require a safe initial local password."""
    password: str = Field(min_length=12, max_length=72)

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        """Reject credentials that bcrypt cannot represent safely."""
        if len(value.encode()) > 72 or '\x00' in value:
            raise ValueError('Password must contain no null characters and be at most 72 UTF-8 bytes')
        return value


class UserResponse(UserInput):
    """Expose account metadata without credentials."""
    model_config = ConfigDict(extra='ignore')
    id: str
    authSource: Literal['local']
    lastLogin: str | None = None
    mustChangePassword: bool = False
    createdAt: str
    updatedAt: str


class RoleInput(BaseModel):
    """Accept a fixed role name and validated permission set."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: RoleName
    description: str = Field(default='', max_length=1000)
    permissions: list[Permission] = Field(max_length=6)

    @field_validator('permissions')
    @classmethod
    def unique_permissions(cls, value: list[str]) -> list[str]:
        """Reject duplicate permission entries."""
        if len(value) != len(set(value)):
            raise ValueError('Duplicate permission')
        return value


class RoleResponse(RoleInput):
    """Expose the persisted role definition."""
    model_config = ConfigDict(extra='ignore')
    id: str
    createdAt: str
    updatedAt: str


class AuditResponse(BaseModel):
    """Expose a password-free audit event."""
    id: str
    timestamp: str
    userId: str | None
    userName: str
    action: str
    entityType: str
    entityId: str | None
    details: str


class UserPage(BaseModel):
    """Return a bounded user page."""
    items: list[UserResponse]
    total: int
    limit: int
    offset: int


class RolePage(BaseModel):
    """Return a bounded role page."""
    items: list[RoleResponse]
    total: int
    limit: int
    offset: int


class AuditPage(BaseModel):
    """Return a bounded audit page."""
    items: list[AuditResponse]
    total: int
    limit: int
    offset: int
