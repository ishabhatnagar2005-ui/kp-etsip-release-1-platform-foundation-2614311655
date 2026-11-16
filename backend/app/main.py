"""Construct the API and manage its MongoDB client lifecycle."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from app.auth.router import router
from app.portfolios.router import router as portfolio_router
from app.applications.router import router as application_router
from app.dashboard.router import router as dashboard_router
from app.admin.router import router as admin_router
from app.core.config import Settings
from app.core.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect, initialize indexes and seed, then close the client."""
    settings = Settings()
    settings.validate_secrets()
    client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        db = client.get_database(settings.mongodb_db)
        await client.admin.command("ping")
        await db.users.create_index("email", unique=True)
        await db.roles.create_index("name", unique=True)
        await db.audit_logs.create_index([("timestamp", -1), ("_id", -1)])
        await db.audit_logs.create_index([("userId", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("action", 1), ("timestamp", -1)])
        await db.portfolios.create_index("name", unique=True)
        await db.applications.create_index("portfolioId")
        await db.applications.create_index("name", unique=True)
        if settings.seed_on_startup:
            await seed_database(db, settings)
        app.state.db = db
        app.state.settings = settings
        yield
    finally:
        await client.close()


app = FastAPI(title="KP ETSIP Identity API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in Settings().cors_origins.split(",") if origin.strip()], allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.include_router(router)
app.include_router(portfolio_router)
app.include_router(application_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
