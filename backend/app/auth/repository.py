"""Persist identity and audit operations in MongoDB."""
from datetime import datetime, timezone
from pymongo.asynchronous.database import AsyncDatabase


def now() -> str:
    """Return a UTC ISO timestamp for document fields."""
    return datetime.now(timezone.utc).isoformat()


class AuthRepository:
    """Read and mutate local identity records and their audit history."""
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def by_email(self, email: str) -> dict | None:
        """Find a normalized email address."""
        return await self.db.users.find_one({"email": email})

    async def update(self, user: dict, fields: dict, increment_version: bool = False) -> None:
        """Persist identity changes and optionally revoke existing tokens."""
        update = {"$set": {**fields, "updatedAt": now()}}
        if increment_version:
            update["$inc"] = {"tokenVersion": 1}
        await self.db.users.update_one({"_id": user["_id"]}, update)

    async def audit(self, user: dict | None, action: str, details: str) -> None:
        """Record a password-free identity event."""
        stamp = now()
        await self.db.audit_logs.insert_one({"timestamp": stamp, "createdAt": stamp, "updatedAt": stamp, "userId": str(user["_id"]) if user else None, "userName": user["name"] if user else "Unknown user", "action": action, "entityType": "user", "entityId": str(user["_id"]) if user else None, "details": details})
