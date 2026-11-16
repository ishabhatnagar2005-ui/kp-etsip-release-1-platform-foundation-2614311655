"""Expose the lifespan-owned MongoDB database to requests."""
from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase


def get_database(request: Request) -> AsyncDatabase:
    """Return the database associated with the active application."""
    return request.app.state.db
