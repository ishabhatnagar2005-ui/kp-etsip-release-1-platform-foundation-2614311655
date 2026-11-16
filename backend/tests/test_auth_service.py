"""Exercise identity services directly against isolated real MongoDB databases."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException
from jose import jwt
from pymongo import AsyncMongoClient

from app.auth.repository import AuthRepository
from app.auth.service import change_password, login
from app.core.security import hash_password, verify_password

PASSWORD = "Original-password-123"
NEW_PASSWORD = "Replacement-password-456"
SECRET = "test-secret-with-more-than-thirty-two-characters"


@asynccontextmanager
async def repository():
    """Create and clean up a unique test database on the local MongoDB server."""
    client = AsyncMongoClient(os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=5000)
    name = "etsip_auth_service_test_" + uuid.uuid4().hex
    db = client[name]
    try:
        yield AuthRepository(db)
    finally:
        await client.drop_database(name)
        await client.close()


async def add_user(repo: AuthRepository, status: str = "Active") -> dict:
    """Insert an account with a real password hash for the service tests."""
    user = {"name": "Test Engineer", "email": "engineer@example.com", "role": "Engineer", "status": status,
            "passwordHash": await hash_password(PASSWORD), "tokenVersion": 3, "mustChangePassword": True}
    result = await repo.db.users.insert_one(user)
    user["_id"] = result.inserted_id
    return user


def test_login_normalizes_email_returns_token_and_persists_audit() -> None:
    async def scenario() -> None:
        async with repository() as repo:
            user = await add_user(repo)
            result = await login(repo, "  ENGINEER@EXAMPLE.COM  ", PASSWORD, SECRET)
            claims = jwt.decode(result["token"], SECRET, algorithms=["HS256"])
            assert claims["sub"] == str(user["_id"])
            assert claims["ver"] == 3
            assert result["user"].email == user["email"]
            assert "passwordHash" not in result["user"].model_dump()
            stored = await repo.db.users.find_one({"_id": user["_id"]})
            assert stored["lastLogin"]
            audit = await repo.db.audit_logs.find_one({"details": "Login succeeded"})
            assert audit["userId"] == str(user["_id"])
            assert PASSWORD not in str(audit)
    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["unknown", "wrong_password", "inactive"])
def test_login_rejects_invalid_credentials_and_audits(case: str) -> None:
    async def scenario() -> None:
        async with repository() as repo:
            user = await add_user(repo, status="Inactive" if case == "inactive" else "Active")
            email = "missing@example.com" if case == "unknown" else user["email"]
            password = "wrong-password" if case == "wrong_password" else PASSWORD
            with pytest.raises(HTTPException) as error:
                await login(repo, email, password, SECRET)
            assert error.value.status_code == 401
            assert error.value.detail == "Invalid email or password"
            stored = await repo.db.users.find_one({"_id": user["_id"]})
            assert "lastLogin" not in stored
            audit = await repo.db.audit_logs.find_one({"details": "Login failed"})
            assert audit["userId"] == (None if case == "unknown" else str(user["_id"]))
            assert password not in str(audit)
    asyncio.run(scenario())


@pytest.mark.parametrize("current,new,detail", [
    ("wrong-password", NEW_PASSWORD, "Current password is incorrect"),
    (PASSWORD, PASSWORD, "New password must differ from current password"),
])
def test_change_password_rejects_invalid_changes_without_mutation(current: str, new: str, detail: str) -> None:
    async def scenario() -> None:
        async with repository() as repo:
            user = await add_user(repo)
            with pytest.raises(HTTPException) as error:
                await change_password(repo, user, current, new)
            assert error.value.status_code == 400
            assert error.value.detail == detail
            stored = await repo.db.users.find_one({"_id": user["_id"]})
            assert stored["passwordHash"] == user["passwordHash"]
            assert stored["tokenVersion"] == 3
            assert stored["mustChangePassword"] is True
            assert await repo.db.audit_logs.count_documents({"details": "Password changed"}) == 0
    asyncio.run(scenario())


def test_change_password_persists_new_hash_revocation_and_audit() -> None:
    async def scenario() -> None:
        async with repository() as repo:
            user = await add_user(repo)
            await change_password(repo, user, PASSWORD, NEW_PASSWORD)
            stored = await repo.db.users.find_one({"_id": user["_id"]})
            assert stored["passwordHash"] != user["passwordHash"]
            assert await verify_password(NEW_PASSWORD, stored["passwordHash"])
            assert not await verify_password(PASSWORD, stored["passwordHash"])
            assert stored["tokenVersion"] == 4
            assert stored["mustChangePassword"] is False
            audit = await repo.db.audit_logs.find_one({"details": "Password changed"})
            assert audit["userId"] == str(user["_id"])
            assert PASSWORD not in str(audit) and NEW_PASSWORD not in str(audit)
            result = await login(repo, user["email"], NEW_PASSWORD, SECRET)
            assert jwt.decode(result["token"], SECRET, algorithms=["HS256"])["ver"] == 4
    asyncio.run(scenario())
