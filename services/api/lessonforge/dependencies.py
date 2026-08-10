from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import Membership, Organization, User
from .schemas import CurrentUser, Role
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請先登入")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = str(payload["sub"])
        organization_id = str(payload["org"])
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登入憑證已失效"
        ) from None

    statement = (
        select(User, Membership, Organization)
        .join(Membership, Membership.user_id == User.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            Membership.organization_id == organization_id,
        )
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或組織權限不存在")
    user, membership, organization = row
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=organization.id,
        organization_name=organization.name,
        role=Role(membership.role),
    )


DependencyCallable = Callable[..., Coroutine[Any, Any, CurrentUser]]


def require_roles(*roles: Role) -> DependencyCallable:
    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="你的角色無法執行此操作"
            )
        return user

    return dependency
