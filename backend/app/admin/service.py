"""Enforce administration invariants and coordinate persistence."""
import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.admin.repository import AdminRepository, project
from app.admin.schema import RoleInput, UserCreate, UserInput
from app.core.security import hash_password


async def get_entity(repo: AdminRepository, collection: str, identifier: str) -> dict:
    """Resolve an entity or report it missing."""
    doc = await repo.get(collection, identifier)
    if doc is None:
        raise HTTPException(404, f'{collection[:-1].title()} not found')
    return doc


async def create_user(repo: AdminRepository, actor: dict, body: UserCreate) -> dict:
    """Create a local user and record a credential-free event."""
    fields = body.model_dump(exclude={'password'})
    if not await repo.portfolios_exist(fields['portfolioAccess']):
        raise HTTPException(422, 'Unknown portfolio assignment')
    fields.update(passwordHash=await hash_password(body.password), lastLogin=None, authSource='local', mustChangePassword=False, tokenVersion=0)
    try:
        doc = await repo.insert('users', fields)
    except DuplicateKeyError as exc:
        raise HTTPException(409, 'Email already exists') from exc
    await repo.audit(actor, 'create', 'user', str(doc['_id']), 'User created')
    return project(doc)


async def update_user(repo: AdminRepository, actor: dict, identifier: str, body: UserInput | None) -> dict:
    """Update or deactivate an account while preserving an active administrator."""
    lock = uuid4().hex
    if not await repo.acquire_admin_lock(lock):
        raise HTTPException(409, 'Another account change is in progress; retry')
    try:
        doc = await get_entity(repo, 'users', identifier)
        fields = body.model_dump() if body else {'status': 'Inactive'}
        if body and not await repo.portfolios_exist(fields['portfolioAccess']):
            raise HTTPException(422, 'Unknown portfolio assignment')
        removing_admin = doc['role'] == 'Administrator' and doc['status'] == 'Active' and (fields.get('role', doc['role']) != 'Administrator' or fields.get('status', doc['status']) != 'Active')
        if str(doc['_id']) == str(actor['_id']) and fields.get('status', doc['status']) == 'Inactive':
            raise HTTPException(409, 'You cannot deactivate your own account')
        if removing_admin and await repo.active_admin_count() <= 1:
            raise HTTPException(409, 'At least one active administrator is required')
        role_changed = fields.get('role', doc['role']) != doc['role']
        revoke = role_changed or fields.get('status', doc['status']) != doc['status']
        try:
            updated = await repo.update('users', doc, fields, revoke=revoke)
        except DuplicateKeyError as exc:
            raise HTTPException(409, 'Email already exists') from exc
        if updated is None:
            raise HTTPException(404, 'User not found')
        await repo.audit(actor, 'delete' if body is None else 'edit', 'user', identifier, 'User deactivated' if body is None else 'User updated')
        if role_changed:
            await repo.audit(actor, 'roleChange', 'user', identifier, 'User role changed')
        return project(updated)
    finally:
        await repo.release_admin_lock(lock)


async def create_role(repo: AdminRepository, actor: dict, body: RoleInput) -> dict:
    """Create a missing fixed role without allowing duplicate names."""
    if body.name == 'Administrator' and 'administer' not in body.permissions:
        raise HTTPException(409, 'Administrator role must retain administer permission')
    try:
        doc = await repo.insert('roles', body.model_dump())
    except DuplicateKeyError as exc:
        raise HTTPException(409, 'Role already exists') from exc
    await repo.audit(actor, 'create', 'role', str(doc['_id']), 'Role created')
    return project(doc)


async def update_role(repo: AdminRepository, actor: dict, identifier: str, body: RoleInput) -> dict:
    """Edit permissions without renaming fixed roles or locking out admins."""
    doc = await get_entity(repo, 'roles', identifier)
    if body.name != doc['name']:
        raise HTTPException(409, 'Role names cannot be changed')
    if body.name == 'Administrator' and 'administer' not in body.permissions:
        raise HTTPException(409, 'Administrator role must retain administer permission')
    updated = await repo.update('roles', doc, body.model_dump())
    if updated is None:
        raise HTTPException(404, 'Role not found')
    await repo.audit(actor, 'edit', 'role', identifier, 'Role updated')
    if set(body.permissions) != set(doc.get('permissions', [])):
        await repo.audit(actor, 'permissionChange', 'role', identifier, 'Role permissions changed')
    return project(updated)


def audit_query(user_id: str | None, action: str | None, start: str | None, end: str | None) -> dict:
    """Build a safe, inclusive UTC timestamp filter from ISO dates or datetimes."""
    def parse(value: str, upper: bool) -> str:
        """Normalize a date or timestamp for lexicographic UTC comparisons."""
        try:
            if len(value) == 10:
                day = date.fromisoformat(value)
                dt = datetime.combine(day + timedelta(days=1) if upper else day, time.min, timezone.utc)
            else:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    raise ValueError('timezone required')
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat()
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, 'Dates must be ISO dates or timezone-aware timestamps') from exc
    query: dict = {}
    if user_id:
        query['userId'] = user_id
    if action:
        query['action'] = action
    if start or end:
        bounds = {}
        if start:
            bounds['$gte'] = parse(start, False)
        if end:
            bounds['$lt' if len(end) == 10 else '$lte'] = parse(end, True)
        if start and end and parse(start, False) > parse(end, True):
            raise HTTPException(422, 'From date must not be after to date')
        query['timestamp'] = bounds
    return query


async def export_audit(repo: AdminRepository, actor: dict, query: dict) -> str:
    """Export matching audit events up to a bounded maximum and audit the export."""
    first = await repo.page('audit_logs', query, 100, 0)
    if first['total'] > 10000:
        raise HTTPException(422, 'Too many audit events to export; narrow the filters')
    rows = first['items']
    for offset in range(100, first['total'], 100):
        rows.extend((await repo.page('audit_logs', query, 100, offset))['items'])
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    columns = ['timestamp', 'userId', 'userName', 'action', 'entityType', 'entityId', 'details']
    writer.writerow(columns)
    for row in rows:
        # Prefix formula-leading cells so spreadsheet software treats them as text.
        values = [str(row.get(key) or '') for key in columns]
        writer.writerow(["'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
    await repo.audit(actor, 'export', 'audit', None, 'Audit log exported')
    return output.getvalue()
