"""Persist application inventory and audit events in MongoDB."""
import re
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from app.auth.repository import now


class ApplicationRepository:
    """Access applications and their portfolio references."""
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def list_page(self, query: dict, limit: int, offset: int) -> tuple[list[dict], int]:
        """Return matching documents and their total count."""
        total = await self.db.applications.count_documents(query)
        docs = await self.db.applications.find(query).sort([("name", 1), ("_id", 1)]).skip(offset).limit(limit).to_list(None)
        return [self.public(doc) for doc in docs], total

    async def get(self, identifier: str) -> dict | None:
        """Find an application by its public identifier."""
        if not ObjectId.is_valid(identifier):
            return None
        return await self.db.applications.find_one({"_id": ObjectId(identifier)})

    async def portfolio_exists(self, identifier: str) -> bool:
        """Check whether the referenced portfolio exists."""
        return ObjectId.is_valid(identifier) and await self.db.portfolios.find_one({"_id": ObjectId(identifier)}) is not None

    @staticmethod
    def public(doc: dict) -> dict:
        """Convert the internal identifier to its API representation."""
        return {**{key: value for key, value in doc.items() if key != "_id"}, "id": str(doc["_id"])}

    async def insert(self, fields: dict) -> dict:
        """Insert an application and return its stored document."""
        stamp = now()
        result = await self.db.applications.insert_one({**fields, "createdAt": stamp, "updatedAt": stamp})
        return await self.db.applications.find_one({"_id": result.inserted_id})

    async def update(self, doc: dict, fields: dict) -> dict | None:
        """Update an existing application and return the stored document."""
        await self.db.applications.update_one({"_id": doc["_id"]}, {"$set": {**fields, "updatedAt": now()}})
        return await self.db.applications.find_one({"_id": doc["_id"]})

    async def delete(self, doc: dict) -> bool:
        """Delete a document if it still exists."""
        return (await self.db.applications.delete_one({"_id": doc["_id"]})).deleted_count == 1

    async def audit(self, user: dict, action: str, identifier: str) -> None:
        """Record a successful mutation without exposing request data."""
        stamp = now()
        await self.db.audit_logs.insert_one({"timestamp": stamp, "createdAt": stamp, "updatedAt": stamp, "userId": str(user["_id"]), "userName": user["name"], "action": action, "entityType": "application", "entityId": identifier, "details": f"Application {action}"})


def filters(user: dict, search: str | None, portfolio_id: str | None, criticality: str | None, risk_level: str | None, lifecycle_status: str | None) -> dict:
    """Build literal search and scope-constrained filter predicates."""
    query: dict = {}
    if user["role"] == "Portfolio Leader":
        allowed = user.get("portfolioAccess", [])
        query["portfolioId"] = {"$in": [portfolio_id] if portfolio_id in allowed else []} if portfolio_id else {"$in": allowed}
    elif portfolio_id:
        query["portfolioId"] = portfolio_id
    if search:
        query["name"] = {"$regex": re.escape(search), "$options": "i"}
    for key, value in (("criticality", criticality), ("riskLevel", risk_level), ("lifecycleStatus", lifecycle_status)):
        if value:
            query[key] = value
    return query
