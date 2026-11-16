"""Persist portfolios and derive their application metrics in MongoDB."""
import re
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from app.auth.repository import now


class PortfolioRepository:
    """Access portfolio, application and audit collections."""
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def list_page(self, query: dict, limit: int, offset: int) -> tuple[list[dict], int]:
        """Fetch a bounded ordered page and total before enrichment."""
        total = await self.db.portfolios.count_documents(query)
        docs = await self.db.portfolios.find(query).sort([("name", 1), ("_id", 1)]).skip(offset).limit(limit).to_list(None)
        return [await self.enrich(doc) for doc in docs], total

    async def get(self, identifier: str) -> dict | None:
        """Find a portfolio by its public identifier."""
        if not ObjectId.is_valid(identifier):
            return None
        return await self.db.portfolios.find_one({"_id": ObjectId(identifier)})

    async def enrich(self, doc: dict) -> dict:
        """Compute count and average without storing derived values."""
        cursor = await self.db.applications.aggregate([
            {"$match": {"portfolioId": str(doc["_id"])}},
            {"$group": {"_id": None, "count": {"$sum": 1}, "quality": {"$avg": "$qualityScore"}}},
        ])
        result = await cursor.to_list(None)
        aggregate = result[0] if result else {}
        quality = aggregate.get("quality")
        return {**{key: value for key, value in doc.items() if key != "_id"}, "id": str(doc["_id"]), "applicationCount": aggregate.get("count", 0),
                "qualityScore": int(quality + 0.5) if quality is not None else None}

    async def insert(self, fields: dict) -> dict:
        """Insert a new portfolio with UTC timestamps."""
        stamp = now()
        doc = {**fields, "createdAt": stamp, "updatedAt": stamp}
        result = await self.db.portfolios.insert_one(doc)
        return await self.db.portfolios.find_one({"_id": result.inserted_id})

    async def update(self, doc: dict, fields: dict) -> dict | None:
        """Persist changes and return the current document."""
        await self.db.portfolios.update_one({"_id": doc["_id"]}, {"$set": {**fields, "updatedAt": now()}})
        return await self.db.portfolios.find_one({"_id": doc["_id"]})

    async def delete(self, doc: dict) -> bool:
        """Delete an existing document and indicate whether it existed."""
        return (await self.db.portfolios.delete_one({"_id": doc["_id"]})).deleted_count == 1

    async def applications(self, identifier: str, limit: int, offset: int) -> tuple[list[dict], int]:
        """List linked application summaries using the stored string reference."""
        query = {"portfolioId": identifier}
        total = await self.db.applications.count_documents(query)
        docs = await self.db.applications.find(query, {"name": 1}).sort([("name", 1), ("_id", 1)]).skip(offset).limit(limit).to_list(None)
        return [{"id": str(doc["_id"]), "name": doc["name"]} for doc in docs], total

    async def audit(self, user: dict, action: str, identifier: str) -> None:
        """Record a successful portfolio mutation."""
        stamp = now()
        await self.db.audit_logs.insert_one({"timestamp": stamp, "createdAt": stamp, "updatedAt": stamp,
            "userId": str(user["_id"]), "userName": user["name"], "action": action,
            "entityType": "portfolio", "entityId": identifier, "details": f"Portfolio {action}"})


def filters(user: dict, search: str | None, status: str | None, product_area: str | None) -> dict:
    """Build safe query predicates and constrain leaders to assignments."""
    query: dict = {}
    if user["role"] == "Portfolio Leader":
        query["_id"] = {"$in": [ObjectId(value) for value in user.get("portfolioAccess", []) if ObjectId.is_valid(value)]}
    if search:
        query["name"] = {"$regex": re.escape(search), "$options": "i"}
    if status:
        query["status"] = status
    if product_area:
        query["productArea"] = product_area
    return query
