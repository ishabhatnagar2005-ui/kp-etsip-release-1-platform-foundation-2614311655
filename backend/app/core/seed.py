"""Seed role definitions and configured local demonstration identities."""
from datetime import datetime, timezone
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import Settings
from app.core.security import ROLES, hash_password


async def seed_database(db: AsyncDatabase, settings: Settings) -> None:
    """Insert missing roles and accounts without resetting existing credentials."""
    now = datetime.now(timezone.utc).isoformat()
    for name, area in (("Payments", "Payments"), ("Customer Platform", "Customer"), ("Data & Analytics", "Data")):
        await db.portfolios.update_one({"name": name}, {"$setOnInsert": {"name": name, "owner": "Portfolio Leader", "description": "", "productArea": area, "status": "Active", "createdAt": now, "updatedAt": now}}, upsert=True)
    payments = await db.portfolios.find_one({"name": "Payments"})
    portfolio_docs = [payments, await db.portfolios.find_one({"name": "Customer Platform"}), await db.portfolios.find_one({"name": "Data & Analytics"})]
    applications = [
        ("Payment Gateway", 0, "Critical", 1, 84, 78, 76, 4, "High"),
        ("Claims Settlement", 0, "High", 2, 88, 83, 71, 2, "Medium"),
        ("Billing Ledger", 0, "High", 2, 91, 88, 81, 1, "Low"),
        ("Provider Payments", 0, "Medium", 3, 79, 74, 65, 3, "Medium"),
        ("Member Portal", 1, "Critical", 1, 86, 82, 72, 3, "High"),
        ("Customer Identity", 1, "High", 1, 92, 89, 85, 1, "Low"),
        ("Care Navigation", 1, "Medium", 2, 81, 77, 69, 2, "Medium"),
        ("Analytics Warehouse", 2, "High", 2, 90, 86, 75, 1, "Low"),
        ("Quality Insights", 2, "Medium", 3, 87, 84, 80, 0, "Low"),
        ("Data Exchange", 2, "High", 2, 76, 73, 61, 5, "High"),
    ]
    for name, index, criticality, tier, health, quality, coverage, critical_defects, risk in applications:
        portfolio = portfolio_docs[index]
        doc = {"name": name, "description": f"Supports {portfolio['name']} workflows.", "portfolioId": str(portfolio['_id']), "productArea": portfolio['productArea'], "businessOwner": "Business Operations", "technologyOwner": "Platform Engineering", "etsOwner": "Enterprise Testing", "criticality": criticality, "tier": tier, "lifecycleStatus": "Active", "technologyStack": "Python, React and MongoDB", "repositoryLink": None, "pipelineLink": None, "applicationHealthScore": health, "qualityScore": quality, "automationCoverage": coverage, "unitTestCoverage": min(100, coverage + 8), "openDefects": critical_defects + 6, "openCriticalDefects": critical_defects, "riskLevel": risk, "createdAt": now, "updatedAt": now}
        await db.applications.update_one({"name": name}, {"$setOnInsert": doc}, upsert=True)
    admin_hash = await hash_password(settings.admin_password)
    demo_hash = await hash_password(settings.demo_password)
    for role, permissions in ROLES.items():
        await db.roles.update_one({"name": role}, {"$setOnInsert": {"name": role, "description": role, "permissions": sorted(permissions), "createdAt": now, "updatedAt": now}}, upsert=True)
        email = {"Administrator": "admin", "Executive": "executive", "Portfolio Leader": "leader", "Engineer": "engineer", "Auditor": "auditor", "Read Only": "readonly"}[role] + "@ketsip.local"
        user = {"name": role, "email": email, "passwordHash": admin_hash if role == "Administrator" else demo_hash, "role": role, "portfolioAccess": [], "status": "Active", "lastLogin": None, "authSource": "local", "managerName": None, "vendorIndicator": False, "defaultLandingPage": None, "mustChangePassword": role == "Administrator", "tokenVersion": 0, "createdAt": now, "updatedAt": now}
        await db.users.update_one({"email": email}, {"$setOnInsert": user}, upsert=True)
    # Assign the demo leader once, without resetting later administrative changes.
    await db.users.update_one({"email": "leader@ketsip.local", "portfolioAccess": [], "demoPortfolioSeeded": {"$exists": False}}, {"$set": {"portfolioAccess": [str(payments["_id"])], "demoPortfolioSeeded": True}})
