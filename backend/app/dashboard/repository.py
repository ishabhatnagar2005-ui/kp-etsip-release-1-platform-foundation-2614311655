"""Read scoped dashboard aggregates from MongoDB."""
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class DashboardRepository:
    """Aggregate portfolio applications using the shared MongoDB client."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def aggregates(self, user: dict, portfolio_id: str | None, product_area: str | None, risk_level: str | None) -> list[dict]:
        """Return per-portfolio sums and counts, including visible empty portfolios."""
        scope: dict = {}
        if user["role"] == "Portfolio Leader":
            scope["_id"] = {"$in": [ObjectId(value) for value in user.get("portfolioAccess", []) if ObjectId.is_valid(value)]}
        if portfolio_id:
            scope = {"$and": [scope, {"_id": ObjectId(portfolio_id)}]}
        app_match: dict = {"$expr": {"$eq": ["$portfolioId", "$$portfolio_id"]}}
        if product_area:
            app_match["productArea"] = product_area
        if risk_level:
            app_match["riskLevel"] = risk_level
        pipeline = [
            {"$match": scope},
            {"$lookup": {
                "from": "applications", "let": {"portfolio_id": {"$toString": "$_id"}},
                "pipeline": [
                    {"$match": app_match},
                    {"$group": {"_id": None, "count": {"$sum": 1},
                        "quality": {"$sum": "$qualityScore"}, "health": {"$sum": "$applicationHealthScore"},
                        "automation": {"$sum": "$automationCoverage"}, "defects": {"$sum": "$openCriticalDefects"},
                        "risk": {"$sum": {"$cond": [{"$eq": ["$riskLevel", "High"]}, 1, 0]}}}},
                ], "as": "metrics",
            }},
            {"$set": {"metrics": {"$arrayElemAt": ["$metrics", 0]}}},
        ]
        if product_area or risk_level:
            pipeline.append({"$match": {"metrics.count": {"$gt": 0}}})
        pipeline.extend([{"$sort": {"name": 1, "_id": 1}}, {"$project": {"name": 1, "metrics": 1}}])
        cursor = await self.db.portfolios.aggregate(pipeline)
        return await cursor.to_list(None)
