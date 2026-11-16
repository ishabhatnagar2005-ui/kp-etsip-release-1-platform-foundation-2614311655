"""Expose permission-gated application inventory endpoints."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from app.applications.repository import ApplicationRepository
from app.applications.schema import Application, ApplicationInput, ApplicationPage
from app.applications.service import create_application, delete_application, edit_application, list_applications, visible
from app.core.security import require_permission

router = APIRouter(prefix="/api/applications", tags=["applications"])
View = Annotated[dict, Depends(require_permission("view"))]
Create = Annotated[dict, Depends(require_permission("create"))]
Edit = Annotated[dict, Depends(require_permission("edit"))]
Delete = Annotated[dict, Depends(require_permission("delete"))]


@router.get("", response_model=ApplicationPage)
async def list_route(request: Request, user: View, search: str | None = Query(None, max_length=200), portfolioId: str | None = Query(None, max_length=24), criticality: Literal["Low", "Medium", "High", "Critical"] | None = None, riskLevel: Literal["Low", "Medium", "High"] | None = None, lifecycleStatus: Literal["Active", "Deprecated", "Retired"] | None = None, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    """List matching visible applications."""
    return await list_applications(ApplicationRepository(request.app.state.db), user, search, portfolioId, criticality, riskLevel, lifecycleStatus, limit, offset)


@router.post("", response_model=Application, status_code=201)
async def create_route(body: ApplicationInput, request: Request, user: Create) -> dict:
    """Create an application within the caller's scope."""
    return await create_application(ApplicationRepository(request.app.state.db), user, body)


@router.get("/{identifier}", response_model=Application)
async def detail_route(identifier: str, request: Request, user: View) -> dict:
    """Return a visible application."""
    repo = ApplicationRepository(request.app.state.db)
    return repo.public(await visible(repo, user, identifier))


@router.put("/{identifier}", response_model=Application)
async def edit_route(identifier: str, body: ApplicationInput, request: Request, user: Edit) -> dict:
    """Update an application within the caller's scope."""
    return await edit_application(ApplicationRepository(request.app.state.db), user, identifier, body)


@router.delete("/{identifier}", status_code=204)
async def delete_route(identifier: str, request: Request, user: Delete) -> Response:
    """Delete an application as an administrator."""
    await delete_application(ApplicationRepository(request.app.state.db), user, identifier)
    return Response(status_code=204)
