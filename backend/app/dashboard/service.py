"""Calculate the executive scorecard from visible inventory."""
from bson import ObjectId
from fastapi import HTTPException
from app.dashboard.repository import DashboardRepository


def average(total: int, count: int) -> int | None:
    """Round a nonnegative integer average half up, or return null when empty."""
    return (2 * total + count) // (2 * count) if count else None


async def executive_dashboard(repo: DashboardRepository, user: dict, portfolio_id: str | None = None, product_area: str | None = None, risk_level: str | None = None) -> dict:
    """Apply scope and filters to all scorecard metrics and portfolio breakdowns."""
    if portfolio_id is not None and not ObjectId.is_valid(portfolio_id):
        raise HTTPException(422, "Invalid portfolio identifier")
    if risk_level is not None and risk_level not in {"Low", "Medium", "High"}:
        raise HTTPException(422, "Invalid risk level")
    rows = await repo.aggregates(user, portfolio_id, product_area, risk_level)
    totals = {key: 0 for key in ("count", "quality", "health", "automation", "defects", "risk")}
    portfolios = []
    for row in rows:
        metrics = row.get("metrics") or {}
        for key in totals:
            totals[key] += metrics.get(key, 0)
        portfolios.append({"id": str(row["_id"]), "name": row["name"],
                           "applicationCount": metrics.get("count", 0),
                           "qualityScore": average(metrics.get("quality", 0), metrics.get("count", 0)),
                           "applicationsAtRisk": metrics.get("risk", 0)})
    count = totals["count"]
    return {"enterpriseQualityScore": average(totals["quality"], count),
            "applicationHealthScore": average(totals["health"], count),
            "automationMaturityScore": average(totals["automation"], count),
            "openCriticalDefects": totals["defects"], "applicationsAtRisk": totals["risk"],
            "totalApplications": count, "totalPortfolios": len(portfolios), "portfolios": portfolios}
