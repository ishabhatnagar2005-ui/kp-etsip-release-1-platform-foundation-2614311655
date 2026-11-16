"""Expose the permission-gated executive dashboard."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request
from app.core.security import require_permission
from app.dashboard.repository import DashboardRepository
from app.dashboard.service import executive_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
View = Annotated[dict, Depends(require_permission("view"))]


@router.get("/executive")
async def executive_route(request: Request, user: View, portfolioId: str | None = Query(None, min_length=1, max_length=24), productArea: str | None = Query(None, min_length=1, max_length=200), riskLevel: Literal["Low", "Medium", "High"] | None = None) -> dict:
    """Return metrics over the caller's filtered visible inventory."""
    return await executive_dashboard(DashboardRepository(request.app.state.db), user, portfolioId, productArea, riskLevel)
