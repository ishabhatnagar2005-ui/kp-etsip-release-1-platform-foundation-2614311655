"""Expose local sign-in and authenticated profile operations."""
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response
from app.auth.repository import AuthRepository
from app.auth.schema import LoginRequest, LoginResponse, PasswordUpdate, ProfileUpdate, UserResponse
from app.auth.service import change_password, login, public_user
from app.core.security import current_user

router = APIRouter(prefix="/api/auth", tags=["identity"])


@router.post("/login", response_model=LoginResponse)
async def sign_in(body: LoginRequest, request: Request) -> dict:
    """Authenticate local credentials and issue a bearer token."""
    return await login(AuthRepository(request.app.state.db), body.email, body.password, request.app.state.settings.jwt_secret)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[dict, Depends(current_user)]) -> UserResponse:
    """Return the current safe profile."""
    return public_user(user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(body: ProfileUpdate, request: Request, user: Annotated[dict, Depends(current_user)]) -> UserResponse:
    """Persist the caller's landing preference."""
    repo = AuthRepository(request.app.state.db)
    await repo.update(user, {"defaultLandingPage": body.defaultLandingPage})
    await repo.audit(user, "edit", "Landing preference changed")
    return public_user({**user, "defaultLandingPage": body.defaultLandingPage})


@router.put("/password", status_code=204)
async def update_password(body: PasswordUpdate, request: Request, user: Annotated[dict, Depends(current_user)]) -> Response:
    """Change the caller's password and revoke existing sessions."""
    await change_password(AuthRepository(request.app.state.db), user, body.currentPassword, body.newPassword)
    return Response(status_code=204)


@router.post("/logout", status_code=204)
async def logout(request: Request, user: Annotated[dict, Depends(current_user)]) -> Response:
    """Revoke the caller's sessions."""
    await AuthRepository(request.app.state.db).update(user, {}, increment_version=True)
    return Response(status_code=204)
