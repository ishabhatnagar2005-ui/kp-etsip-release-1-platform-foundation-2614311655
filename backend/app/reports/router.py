"""Expose scoped application and portfolio reports in JSON or CSV."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.applications.repository import ApplicationRepository, filters as application_filters
from app.applications.schema import ApplicationPage
from app.core.security import current_user, require_permission
from app.portfolios.repository import PortfolioRepository, filters as portfolio_filters
from app.portfolios.schema import PortfolioPage
from app.reports.service import export_report

router = APIRouter(prefix='/api/reports', tags=['reports'])
Actor = Annotated[dict, Depends(current_user)]


async def authorize(request: Request, actor: dict, format: str, allowed: set[str]) -> None:
    """Enforce format-specific permissions and reject unrecognized parameters."""
    if set(request.query_params.keys()) - allowed:
        raise HTTPException(422, 'Unknown report parameter')
    await require_permission('export' if format == 'csv' else 'view')(request, actor)
    if format == 'csv' and actor['role'] == 'Read Only':
        raise HTTPException(403, 'Export denied')


@router.get('/applications', response_model=ApplicationPage)
async def applications(
    request: Request, actor: Actor,
    format: Literal['json', 'csv'] = 'json',
    search: str | None = Query(None, max_length=200),
    portfolioId: str | None = Query(None, max_length=24),
    criticality: Literal['Low', 'Medium', 'High', 'Critical'] | None = None,
    riskLevel: Literal['Low', 'Medium', 'High'] | None = None,
    lifecycleStatus: Literal['Active', 'Deprecated', 'Retired'] | None = None,
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
) -> dict | Response:
    """Return a page or download the complete filtered application report."""
    await authorize(request, actor, format, {'format', 'search', 'portfolioId', 'criticality', 'riskLevel', 'lifecycleStatus', 'limit', 'offset'})
    repo = ApplicationRepository(request.app.state.db)
    query = application_filters(actor, search, portfolioId, criticality, riskLevel, lifecycleStatus)
    if format == 'csv':
        content = await export_report(repo, actor, query, 'applications')
        return Response(content, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="applications.csv"'})
    items, total = await repo.list_page(query, limit, offset)
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset}


@router.get('/portfolios', response_model=PortfolioPage)
async def portfolios(
    request: Request, actor: Actor,
    format: Literal['json', 'csv'] = 'json',
    search: str | None = Query(None, max_length=200),
    status: Literal['Active', 'Archived'] | None = None,
    productArea: str | None = Query(None, max_length=200),
    limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
) -> dict | Response:
    """Return a page or download the complete filtered portfolio report."""
    await authorize(request, actor, format, {'format', 'search', 'status', 'productArea', 'limit', 'offset'})
    repo = PortfolioRepository(request.app.state.db)
    query = portfolio_filters(actor, search, status, productArea)
    if format == 'csv':
        content = await export_report(repo, actor, query, 'portfolios')
        return Response(content, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="portfolios.csv"'})
    items, total = await repo.list_page(query, limit, offset)
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset}
