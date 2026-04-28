from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_refresh_token_ttl_seconds,
    hash_password,
    is_token_type,
    verify_password,
)
from src.database.db_session import create_session
from src.database.redis_session import RedisClient
from src.models.users import UserModel, UserRole
from src.schemes.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

http_bearer = HTTPBearer(auto_error=False)


class AuthService:
    def __init__(self, session: AsyncSession, redis: Redis):
        self.session = session
        self.redis = redis

    async def register(self, payload: UserCreate) -> TokenPairResponse:
        return await self.register_with_role(payload, UserRole.USER)

    async def register_with_role(self, payload: UserCreate, role: UserRole) -> TokenPairResponse:
        existing_user = await self._get_user_by_email(payload.email)
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        user = UserModel(
            username=payload.username,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            birthdate=payload.birthdate,
            role=role,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return await self._build_token_response(user)

    async def login(self, payload: LoginRequest) -> TokenPairResponse:
        user = await self._get_user_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return await self._build_token_response(user)

    async def refresh_tokens(self, payload: RefreshTokenRequest) -> TokenPairResponse:
        try:
            token_payload = decode_access_token(payload.refresh_token)
            user_id = int(token_payload["sub"])
        except (InvalidTokenError, KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            ) from None

        if not is_token_type(token_payload, "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        stored_token = await self.redis.get(self._refresh_key(user_id))
        if stored_token != payload.refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token is no longer valid",
            )

        result = await self.session.execute(
            select(UserModel).options(selectinload(UserModel.team)).where(UserModel.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        return await self._build_token_response(user)

    async def logout(self, refresh_token: str) -> None:
        try:
            token_payload = decode_access_token(refresh_token)
            user_id = int(token_payload["sub"])
        except (InvalidTokenError, KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            ) from None

        if not is_token_type(token_payload, "refresh"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        await self.redis.delete(self._refresh_key(user_id))

    async def update_me(self, current_user: UserResponse, payload: UserUpdate) -> UserResponse:
        result = await self.session.execute(
            select(UserModel).options(selectinload(UserModel.team)).where(UserModel.id == current_user.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if payload.username is not None:
            user.username = payload.username
        if payload.birthdate is not None:
            user.birthdate = payload.birthdate

        await self.session.commit()
        await self.session.refresh(user)
        return UserResponse.model_validate(user)

    async def _get_user_by_email(self, email: str) -> UserModel | None:
        query = select(UserModel).options(selectinload(UserModel.team)).where(UserModel.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _build_token_response(self, user: UserModel) -> TokenPairResponse:
        user_response = UserResponse.model_validate(user)
        access_token = create_access_token(str(user.id), user.role.value)
        refresh_token = create_refresh_token(str(user.id), user.role.value)
        await self.redis.set(
            self._refresh_key(user.id),
            refresh_token,
            ex=get_refresh_token_ttl_seconds(),
        )
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_response,
        )

    @staticmethod
    def _refresh_key(user_id: int) -> str:
        return f"auth:refresh:{user_id}"


def get_redis() -> Redis:
    return RedisClient.get_client()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    session: AsyncSession = Depends(create_session),
) -> UserResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None

    if not is_token_type(payload, "access"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    result = await session.execute(
        select(UserModel).options(selectinload(UserModel.team)).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return UserResponse.model_validate(user)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    session: AsyncSession = Depends(create_session),
) -> UserResponse | None:
    if credentials is None:
        return None

    return await get_current_user(credentials=credentials, session=session)


def require_roles(*allowed_roles: UserRole):
    allowed_role_values = {role.value for role in allowed_roles}

    def _ensure_allowed_role(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
        if current_user.role.value not in allowed_role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _ensure_allowed_role


require_moderator = require_roles(UserRole.MODERATOR)
