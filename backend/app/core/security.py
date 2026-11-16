"""Provide password hashing, token issuance, and fail-closed access guards."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from bson import ObjectId
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.concurrency import run_in_threadpool

passwords = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)
ROLES = {
    "Administrator": {"view", "create", "edit", "delete", "export", "administer"},
    "Executive": {"view", "export"},
    "Portfolio Leader": {"view", "create", "edit", "export"},
    "Engineer": {"view", "create", "edit", "export"},
    "Auditor": {"view", "export"},
    "Read Only": {"view"},
}


async def hash_password(password: str) -> str:
    """Hash a password without blocking the event loop."""
    return await run_in_threadpool(passwords.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    """Compare credentials without blocking the event loop."""
    if len(password.encode()) > 72 or "\x00" in password:
        return False
    return await run_in_threadpool(passwords.verify, password, password_hash)


def issue_token(user: dict, secret: str) -> str:
    """Issue an eight-hour bearer token tied to the account version."""
    return jwt.encode({"sub": str(user["_id"]), "userId": str(user["_id"]),
                       "role": user["role"], "ver": user.get("tokenVersion", 0),
                       "exp": datetime.now(timezone.utc) + timedelta(hours=8)}, secret, algorithm="HS256")


async def current_user(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> dict:
    """Resolve active identity and reject invalid, revoked, or stale tokens."""
    unauthorized = HTTPException(status_code=401, detail="Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        claims = jwt.decode(credentials.credentials, request.app.state.settings.jwt_secret, algorithms=["HS256"], options={"require_exp": True})
        subject = claims.get("sub")
        if not isinstance(subject, str) or not ObjectId.is_valid(subject):
            raise unauthorized
    except JWTError as exc:
        raise unauthorized from exc
    user = await request.app.state.db.users.find_one({"_id": ObjectId(subject), "status": "Active"})
    if not user or user.get("role") not in ROLES or claims.get("role") != user["role"] or claims.get("ver") != user.get("tokenVersion", 0):
        raise unauthorized
    return user


def require_permission(permission: str):
    """Build a guard that intersects stored permissions with fixed role limits."""
    async def guard(request: Request, user: Annotated[dict, Depends(current_user)]) -> dict:
        """Deny unknown permissions, missing roles, and first-use accounts."""
        role = await request.app.state.db.roles.find_one({"name": user["role"]})
        if user.get("mustChangePassword") or permission not in ROLES.get(user["role"], set()) or not role or permission not in role.get("permissions", []):
            raise HTTPException(status_code=403, detail="Permission denied")
        return user
    return guard
