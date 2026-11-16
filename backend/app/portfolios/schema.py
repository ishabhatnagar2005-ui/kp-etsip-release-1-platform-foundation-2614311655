"""Validate portfolio inputs and public inventory responses."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class PortfolioInput(BaseModel):
    """Accept editable portfolio fields."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    owner: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=4000)
    productArea: str = Field(default="", max_length=200)
    status: Literal["Active", "Archived"] = "Active"


class Portfolio(PortfolioInput):
    """Expose a portfolio and its computed application metrics."""
    id: str
    applicationCount: int
    qualityScore: int | None
    createdAt: str
    updatedAt: str


class PortfolioPage(BaseModel):
    """Return a bounded set of portfolios."""
    items: list[Portfolio]
    total: int
    limit: int
    offset: int


class ApplicationSummary(BaseModel):
    """Expose linked application identifiers and names."""
    id: str
    name: str


class ApplicationPage(BaseModel):
    """Return bounded linked application summaries."""
    items: list[ApplicationSummary]
    total: int
    limit: int
    offset: int
