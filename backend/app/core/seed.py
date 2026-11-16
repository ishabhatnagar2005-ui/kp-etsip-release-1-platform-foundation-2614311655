"""Seed role definitions and configured local demonstration identities."""
from datetime import datetime, timezone
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import Settings
from app.core.security import ROLES, hash_password


async def seed_database(db: AsyncDatabase, settings: Settings) -> None:
    """Insert missing roles and accounts without resetting existing credentials."""
    now = datetime.now(timezone.utc).isoformat()
    admin_hash = await hash_password(settings.admin_password)
    demo_hash = await hash_password(settings.demo_password)
    for role, permissions in ROLES.items():
        await db.roles.update_one({"name": role}, {"$setOnInsert": {"name": role, "description": role, "permissions": sorted(permissions), "createdAt": now, "updatedAt": now}}, upsert=True)
        email = {"Administrator": "admin", "Executive": "executive", "Portfolio Leader": "leader", "Engineer": "engineer", "Auditor": "auditor", "Read Only": "readonly"}[role] + "@ketsip.local"
        user = {"name": role, "email": email, "passwordHash": admin_hash if role == "Administrator" else demo_hash, "role": role, "portfolioAccess": [], "status": "Active", "lastLogin": None, "authSource": "local", "managerName": None, "vendorIndicator": False, "defaultLandingPage": None, "mustChangePassword": role == "Administrator", "tokenVersion": 0, "createdAt": now, "updatedAt": now}
        await db.users.update_one({"email": email}, {"$setOnInsert": user}, upsert=True)
