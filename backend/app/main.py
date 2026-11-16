"""Construct the API and manage its MongoDB client lifecycle."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from app.auth.router import router
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
        if settings.seed_on_startup:
            await seed_database(db, settings)
        app.state.db = db
        app.state.settings = settings
        yield
    finally:
        await client.close()


app = FastAPI(title="KP ETSIP Identity API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in Settings().cors_origins.split(",") if origin.strip()], allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"])
app.include_router(router)
