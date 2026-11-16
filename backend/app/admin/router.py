"""Expose administrator-only account and role management and scoped audit access."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from app.admin.repository import AdminRepository, project
from app.admin.schema import AuditPage, RoleInput, RolePage, RoleResponse, UserCreate, UserInput, UserPage, UserResponse
from app.admin.service import audit_query, create_role, create_user, export_audit, get_entity, update_role, update_user
from app.core.security import require_permission

router = APIRouter(prefix='/api', tags=['administration'])


async def administrator(user: Annotated[dict, Depends(require_permission('administer'))]) -> dict:
    """Require both the fixed administrator role and its stored permission."""
    if user['role'] != 'Administrator':
        raise HTTPException(403, 'Only administrators manage users and roles')
    return user


async def audit_reader(user: Annotated[dict, Depends(require_permission('view'))]) -> dict:
    """Allow only administrators and auditors to inspect audit events."""
    if user['role'] not in ('Administrator', 'Auditor'):
        raise HTTPException(403, 'Audit access denied')
    return user


async def audit_exporter(user: Annotated[dict, Depends(require_permission('export'))]) -> dict:
    """Allow only administrators and auditors with export permission."""
    if user['role'] not in ('Administrator', 'Auditor'):
        raise HTTPException(403, 'Audit export denied')
    return user


Admin = Annotated[dict, Depends(administrator)]
AuditReader = Annotated[dict, Depends(audit_reader)]
AuditExporter = Annotated[dict, Depends(audit_exporter)]


@router.get('/users', response_model=UserPage)
async def users(request: Request, actor: Admin, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    """List account metadata without credentials."""
    return await AdminRepository(request.app.state.db).page('users', {}, limit, offset)


@router.post('/users', response_model=UserResponse, status_code=201)
async def user_create(body: UserCreate, request: Request, actor: Admin) -> dict:
    """Create an account."""
    return await create_user(AdminRepository(request.app.state.db), actor, body)


@router.get('/users/{identifier}', response_model=UserResponse)
async def user_detail(identifier: str, request: Request, actor: Admin) -> dict:
    """Return one account's safe metadata."""
    return project(await get_entity(AdminRepository(request.app.state.db), 'users', identifier))


@router.put('/users/{identifier}', response_model=UserResponse)
async def user_edit(identifier: str, body: UserInput, request: Request, actor: Admin) -> dict:
    """Edit an account and its access assignments."""
    return await update_user(AdminRepository(request.app.state.db), actor, identifier, body)


@router.delete('/users/{identifier}', status_code=204)
async def user_deactivate(identifier: str, request: Request, actor: Admin) -> Response:
    """Deactivate an account while retaining its history."""
    await update_user(AdminRepository(request.app.state.db), actor, identifier, None)
    return Response(status_code=204)


@router.get('/roles', response_model=RolePage)
async def roles(request: Request, actor: Admin, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    """List fixed role definitions."""
    return await AdminRepository(request.app.state.db).page('roles', {}, limit, offset)


@router.post('/roles', response_model=RoleResponse, status_code=201)
async def role_create(body: RoleInput, request: Request, actor: Admin) -> dict:
    """Create a missing fixed role definition."""
    return await create_role(AdminRepository(request.app.state.db), actor, body)


@router.put('/roles/{identifier}', response_model=RoleResponse)
async def role_edit(identifier: str, body: RoleInput, request: Request, actor: Admin) -> dict:
    """Update a role's description and permissions."""
    return await update_role(AdminRepository(request.app.state.db), actor, identifier, body)


@router.get('/audit-logs', response_model=AuditPage)
async def audit_logs(request: Request, actor: AuditReader, userId: str | None = Query(None, max_length=100), action: Literal['login', 'create', 'edit', 'delete', 'roleChange', 'permissionChange', 'export'] | None = None, from_: str | None = Query(None, alias='from', max_length=40), to: str | None = Query(None, max_length=40), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)) -> dict:
    """List matching audit events with bounded pagination."""
    return await AdminRepository(request.app.state.db).page('audit_logs', audit_query(userId, action, from_, to), limit, offset)


@router.get('/audit-logs/export')
async def audit_csv(request: Request, actor: AuditExporter, userId: str | None = Query(None, max_length=100), action: Literal['login', 'create', 'edit', 'delete', 'roleChange', 'permissionChange', 'export'] | None = None, from_: str | None = Query(None, alias='from', max_length=40), to: str | None = Query(None, max_length=40)) -> Response:
    """Download matching audit events as CSV."""
    content = await export_audit(AdminRepository(request.app.state.db), actor, audit_query(userId, action, from_, to))
    return Response(content, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="audit-logs.csv"'})
