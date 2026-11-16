"""Enforce application visibility and mutation rules."""
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.applications.repository import ApplicationRepository, filters
from app.applications.schema import ApplicationInput


async def list_applications(repo: ApplicationRepository, user: dict, search: str | None, portfolio_id: str | None, criticality: str | None, risk_level: str | None, lifecycle_status: str | None, limit: int, offset: int) -> dict:
    """Return a bounded page within the caller's portfolio scope."""
    items, total = await repo.list_page(filters(user, search, portfolio_id, criticality, risk_level, lifecycle_status), limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def check_scope(user: dict, portfolio_id: str) -> None:
    """Deny leaders access to unassigned portfolios."""
    if user["role"] == "Portfolio Leader" and portfolio_id not in user.get("portfolioAccess", []):
        raise HTTPException(403, "Portfolio outside assigned scope")


async def visible(repo: ApplicationRepository, user: dict, identifier: str) -> dict:
    """Resolve an existing application and enforce visibility."""
    doc = await repo.get(identifier)
    if doc is None:
        raise HTTPException(404, "Application not found")
    check_scope(user, doc["portfolioId"])
    return doc


async def validate_portfolio(repo: ApplicationRepository, user: dict, identifier: str) -> None:
    """Validate portfolio reference and target scope before writing."""
    if not await repo.portfolio_exists(identifier):
        raise HTTPException(422, "Portfolio does not exist")
    check_scope(user, identifier)


def check_writer(user: dict) -> None:
    """Enforce fixed role limits independently of editable permissions."""
    if user["role"] not in ("Administrator", "Portfolio Leader", "Engineer"):
        raise HTTPException(403, "Cannot change applications")


async def create_application(repo: ApplicationRepository, user: dict, body: ApplicationInput) -> dict:
    """Create and audit a validated application."""
    check_writer(user)
    await validate_portfolio(repo, user, body.portfolioId)
    try:
        doc = await repo.insert(body.model_dump(mode="json"))
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Application name already exists") from exc
    await repo.audit(user, "create", str(doc["_id"]))
    return repo.public(doc)


async def edit_application(repo: ApplicationRepository, user: dict, identifier: str, body: ApplicationInput) -> dict:
    """Update an application only when both old and new scopes are allowed."""
    check_writer(user)
    doc = await visible(repo, user, identifier)
    await validate_portfolio(repo, user, body.portfolioId)
    try:
        updated = await repo.update(doc, body.model_dump(mode="json"))
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Application name already exists") from exc
    if updated is None:
        raise HTTPException(404, "Application not found")
    await repo.audit(user, "edit", identifier)
    return repo.public(updated)


async def delete_application(repo: ApplicationRepository, user: dict, identifier: str) -> None:
    """Delete and audit an application as an administrator only."""
    if user["role"] != "Administrator":
        raise HTTPException(403, "Only administrators can delete applications")
    doc = await visible(repo, user, identifier)
    if not await repo.delete(doc):
        raise HTTPException(404, "Application not found")
    await repo.audit(user, "delete", identifier)
