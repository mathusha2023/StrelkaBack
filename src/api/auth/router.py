from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db_session import create_session
from src.schemes.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from src.models.users import UserRole
from src.services.auth import AuthService, get_current_user, get_redis

router = APIRouter(tags=["Authorization"], prefix="/auth")


@router.post(
    "/register",
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
)
async def register_user(
    payload: UserCreate,
    session: AsyncSession = Depends(create_session),
    redis: Redis = Depends(get_redis),
) -> TokenPairResponse:
    return await AuthService(session, redis).register(payload)


@router.post(
    "/register/moderator",
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new moderator",
)
async def register_moderator(
    payload: UserCreate,
    session: AsyncSession = Depends(create_session),
    redis: Redis = Depends(get_redis),
) -> TokenPairResponse:
    return await AuthService(session, redis).register_with_role(payload, UserRole.MODERATOR)


@router.post("/login", response_model=TokenPairResponse, summary="Login user")
async def login_user(
    payload: LoginRequest,
    session: AsyncSession = Depends(create_session),
    redis: Redis = Depends(get_redis),
) -> TokenPairResponse:
    return await AuthService(session, redis).login(payload)


@router.post("/refresh", response_model=TokenPairResponse, summary="Refresh tokens")
async def refresh_tokens(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(create_session),
    redis: Redis = Depends(get_redis),
) -> TokenPairResponse:
    return await AuthService(session, redis).refresh_tokens(payload)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Logout user")
async def logout_user(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(create_session),
    redis: Redis = Depends(get_redis),
) -> None:
    await AuthService(session, redis).logout(payload.refresh_token)


@router.get("/me", response_model=UserResponse, summary="Get current user")
async def get_me(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    return current_user


@router.patch("/me", response_model=UserResponse, summary="Update current user")
async def update_me(
    payload: UserUpdate,
    current_user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(create_session),
    redis: Redis = Depends(get_redis),
) -> UserResponse:
    return await AuthService(session, redis).update_me(current_user, payload)
