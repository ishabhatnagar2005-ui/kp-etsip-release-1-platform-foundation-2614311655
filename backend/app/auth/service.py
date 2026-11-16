"""Implement identity workflows and safe profile projections."""
from fastapi import HTTPException
from app.auth.repository import AuthRepository, now
from app.auth.schema import UserResponse
from app.core.security import ROLES, hash_password, issue_token, verify_password


def public_user(user: dict) -> UserResponse:
    """Project an account without exposing stored credentials."""
    return UserResponse(id=str(user["_id"]), name=user["name"], email=user["email"], role=user["role"], portfolioAccess=user.get("portfolioAccess", []), defaultLandingPage=user.get("defaultLandingPage"), mustChangePassword=user.get("mustChangePassword", False), effectivePermissions=user.get("effectivePermissions", []))


async def login(repo: AuthRepository, email: str, password: str, secret: str) -> dict:
    """Authenticate an active account and audit the outcome."""
    user = await repo.by_email(email.strip().lower())
    valid = bool(user and user.get("status") == "Active" and await verify_password(password, user["passwordHash"]))
    if not valid:
        await repo.audit(user, "login", "Login failed")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await repo.update(user, {"lastLogin": now()})
    await repo.audit(user, "login", "Login succeeded")
    role = await repo.db.roles.find_one({"name": user["role"]})
    user["effectivePermissions"] = sorted(ROLES[user["role"]].intersection(role.get("permissions", []) if role else []))
    return {"token": issue_token(user, secret), "user": public_user(user)}


async def change_password(repo: AuthRepository, user: dict, current: str, new: str) -> None:
    """Change a verified password and invalidate all prior tokens."""
    if not await verify_password(current, user["passwordHash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if await verify_password(new, user["passwordHash"]):
        raise HTTPException(status_code=400, detail="New password must differ from current password")
    await repo.update(user, {"passwordHash": await hash_password(new), "mustChangePassword": False}, increment_version=True)
    await repo.audit(user, "edit", "Password changed")
