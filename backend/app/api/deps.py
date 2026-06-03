import uuid
from collections.abc import Generator
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import get_tenant_engine, landlord_engine
from app.models import Tenant, TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_landlord_db() -> Generator[Session, None, None]:
    with Session(landlord_engine) as session:
        yield session


LandlordSessionDep = Annotated[Session, Depends(get_landlord_db)]


def resolve_tenant_id(request: Request) -> str:
    # 1. Check Header
    tenant_id = request.headers.get("x-tenant-id")
    if tenant_id:
        return tenant_id

    # 2. Check JWT Authorization Header
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
            )
            token_tenant_id = payload.get("tenant_id")
            if token_tenant_id:
                return str(token_tenant_id)
        except (InvalidTokenError, ValidationError):
            pass

    # 3. Fallback for backward compatibility (e.g. tests, default landlord schema)
    return "default"


def get_db(request: Request) -> Generator[Session, None, None]:
    tenant_id = resolve_tenant_id(request)

    if tenant_id == "default":
        db_uri = str(settings.SQLALCHEMY_DATABASE_URI)
    else:
        # Fetch tenant info from the landlord database
        with Session(landlord_engine) as landlord_session:
            tenant = landlord_session.get(Tenant, tenant_id)
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tenant '{tenant_id}' does not exist or is inactive.",
                )
            if not tenant.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tenant '{tenant_id}' is inactive.",
                )
            db_uri = tenant.db_uri

    # Get or create cached engine for the tenant
    tenant_engine = get_tenant_engine(tenant_id, db_uri)
    with Session(tenant_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    # Try parsing string to UUID (needed for SQLite support)
    user_id: Any = None
    try:
        user_id = uuid.UUID(token_data.sub) if isinstance(token_data.sub, str) else token_data.sub
    except (ValueError, TypeError):
        user_id = token_data.sub


    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user



CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
