"""Validate application inventory fields and responses."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ApplicationInput(BaseModel):
    """Accept editable application fields with bounded, strict values."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    portfolioId: str = Field(min_length=1, max_length=24)
    productArea: str = Field(default="", max_length=200)
    businessOwner: str = Field(default="", max_length=200)
    technologyOwner: str = Field(default="", max_length=200)
    etsOwner: str = Field(default="", max_length=200)
    criticality: Literal["Low", "Medium", "High", "Critical"] = "Medium"
    tier: int = Field(default=1, strict=True, ge=1, le=4)
    lifecycleStatus: Literal["Active", "Deprecated", "Retired"] = "Active"
    technologyStack: str = Field(default="", max_length=4000)
    repositoryLink: HttpUrl | None = None
    pipelineLink: HttpUrl | None = None
    applicationHealthScore: int = Field(default=0, strict=True, ge=0, le=100)
    qualityScore: int = Field(default=0, strict=True, ge=0, le=100)
    automationCoverage: int = Field(default=0, strict=True, ge=0, le=100)
    unitTestCoverage: int = Field(default=0, strict=True, ge=0, le=100)
    openDefects: int = Field(default=0, strict=True, ge=0)
    openCriticalDefects: int = Field(default=0, strict=True, ge=0)
    riskLevel: Literal["Low", "Medium", "High"] = "Low"

    @field_validator("repositoryLink", "pipelineLink")
    @classmethod
    def safe_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        """Reject URLs containing embedded credentials."""
        if value and (value.username or value.password):
            raise ValueError("URL must not contain credentials")
        return value


class Application(ApplicationInput):
    """Expose a stored application with its identifier and timestamps."""
    id: str
    createdAt: str
    updatedAt: str


class ApplicationPage(BaseModel):
    """Return a bounded page of applications."""
    items: list[Application]
    total: int
    limit: int
    offset: int
