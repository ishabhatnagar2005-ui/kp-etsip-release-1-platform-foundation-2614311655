"""Enforce portfolio-specific rules and coordinate persistent operations."""
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.portfolios.repository import PortfolioRepository, filters
from app.portfolios.schema import PortfolioInput


async def list_portfolios(repo: PortfolioRepository, user: dict, search: str | None, status: str | None, product_area: str | None, limit: int, offset: int) -> dict:
    """Return only visible matching portfolios and their metrics."""
    items, total = await repo.list_page(filters(user, search, status, product_area), limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def visible(repo: PortfolioRepository, user: dict, identifier: str) -> dict:
    """Resolve a portfolio and enforce assigned leader scope."""
    doc = await repo.get(identifier)
    if doc is None:
        raise HTTPException(404, "Portfolio not found")
    if user["role"] == "Portfolio Leader" and str(doc["_id"]) not in user.get("portfolioAccess", []):
        raise HTTPException(403, "Portfolio outside assigned scope")
    return doc


async def create_portfolio(repo: PortfolioRepository, user: dict, body: PortfolioInput) -> dict:
    """Create an administrator-owned portfolio and record the action."""
    if user["role"] != "Administrator":
        raise HTTPException(403, "Only administrators can create portfolios")
    try:
        doc = await repo.insert(body.model_dump())
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Portfolio name already exists") from exc
    await repo.audit(user, "create", str(doc["_id"]))
    return await repo.enrich(doc)


async def edit_portfolio(repo: PortfolioRepository, user: dict, identifier: str, body: PortfolioInput) -> dict:
    """Edit an authorized portfolio and record the action."""
    if user["role"] not in ("Administrator", "Portfolio Leader"):
        raise HTTPException(403, "Cannot edit portfolios")
    doc = await visible(repo, user, identifier)
    try:
        updated = await repo.update(doc, body.model_dump())
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Portfolio name already exists") from exc
    if updated is None:
        raise HTTPException(404, "Portfolio not found")
    await repo.audit(user, "edit", identifier)
    return await repo.enrich(updated)


async def delete_portfolio(repo: PortfolioRepository, user: dict, identifier: str) -> None:
    """Reject nonempty portfolios and audit an administrator deletion."""
    if user["role"] != "Administrator":
        raise HTTPException(403, "Only administrators can delete portfolios")
    doc = await visible(repo, user, identifier)
    _, total = await repo.applications(identifier, 1, 0)
    if total:
        raise HTTPException(409, "Portfolio contains applications")
    if not await repo.delete(doc):
        raise HTTPException(404, "Portfolio not found")
    await repo.audit(user, "delete", identifier)
