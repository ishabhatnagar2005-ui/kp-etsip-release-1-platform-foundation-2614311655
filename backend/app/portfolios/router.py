"""Expose authorized portfolio inventory endpoints."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from app.core.security import require_permission
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schema import ApplicationPage, Portfolio, PortfolioInput, PortfolioPage
from app.portfolios.service import create_portfolio, delete_portfolio, edit_portfolio, list_portfolios, visible

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])
View = Annotated[dict, Depends(require_permission("view"))]
Create = Annotated[dict, Depends(require_permission("create"))]
Edit = Annotated[dict, Depends(require_permission("edit"))]
Delete = Annotated[dict, Depends(require_permission("delete"))]


@router.get("", response_model=PortfolioPage)
async def list_route(request: Request, user: View, search: str | None = Query(None, max_length=200), status: Literal["Active", "Archived"] | None = None, productArea: str | None = Query(None, max_length=200), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    """List matching visible portfolios."""
    return await list_portfolios(PortfolioRepository(request.app.state.db), user, search, status, productArea, limit, offset)


@router.post("", response_model=Portfolio, status_code=201)
async def create_route(body: PortfolioInput, request: Request, user: Create) -> dict:
    """Create a portfolio as an administrator."""
    return await create_portfolio(PortfolioRepository(request.app.state.db), user, body)


@router.get("/{identifier}", response_model=Portfolio)
async def detail_route(identifier: str, request: Request, user: View) -> dict:
    """Return a visible portfolio with computed metrics."""
    repo = PortfolioRepository(request.app.state.db)
    return await repo.enrich(await visible(repo, user, identifier))


@router.get("/{identifier}/applications", response_model=ApplicationPage)
async def applications_route(identifier: str, request: Request, user: View, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    """List applications linked to a visible portfolio."""
    repo = PortfolioRepository(request.app.state.db)
    await visible(repo, user, identifier)
    items, total = await repo.applications(identifier, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.put("/{identifier}", response_model=Portfolio)
async def edit_route(identifier: str, body: PortfolioInput, request: Request, user: Edit) -> dict:
    """Update a portfolio within the caller's scope."""
    return await edit_portfolio(PortfolioRepository(request.app.state.db), user, identifier, body)


@router.delete("/{identifier}", status_code=204)
async def delete_route(identifier: str, request: Request, user: Delete) -> Response:
    """Delete an empty portfolio as an administrator."""
    await delete_portfolio(PortfolioRepository(request.app.state.db), user, identifier)
    return Response(status_code=204)
