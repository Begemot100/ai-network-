"""
Authentication module for the Distributed AI Network.
Implements JWT-based authentication for API and workers.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlmodel import Session, select

from .config import settings
from .db import get_session
from .models import Worker


# =============================================================================
# PASSWORD HASHING
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def generate_api_key() -> str:
    """Generate a secure API key for workers."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


# =============================================================================
# JWT TOKENS
# =============================================================================

class TokenData(BaseModel):
    """Data extracted from JWT token."""
    sub: str  # Subject (worker_id or admin_id)
    type: str  # Token type: "access", "refresh", "worker"
    exp: datetime
    iat: datetime
    jti: Optional[str] = None  # JWT ID for revocation


class TokenResponse(BaseModel):
    """Response with access and refresh tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def create_access_token(
    subject: str,
    token_type: str = "access",
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expiry_minutes)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": subject,
        "type": token_type,
        "exp": expire,
        "iat": now,
        "jti": secrets.token_urlsafe(16),
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    """Create a JWT refresh token."""
    return create_access_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_expiry_days),
    )


def create_worker_token(worker_id: int) -> str:
    """Create a long-lived token for worker authentication."""
    return create_access_token(
        subject=f"worker:{worker_id}",
        token_type="worker",
        expires_delta=timedelta(days=365),  # Long-lived for workers
    )


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm]
        )
        return TokenData(
            sub=payload["sub"],
            type=payload["type"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            jti=payload.get("jti"),
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# =============================================================================
# SECURITY DEPENDENCIES
# =============================================================================

security = HTTPBearer(auto_error=False)


async def get_current_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """Extract and validate token from request."""
    if credentials is None:
        return None

    return decode_token(credentials.credentials)


async def require_auth(
    token: Optional[TokenData] = Depends(get_current_token),
) -> TokenData:
    """Require valid authentication."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_worker(
    token: TokenData = Depends(require_auth),
    session: Session = Depends(get_session),
) -> Worker:
    """Get the current authenticated worker."""
    if not token.sub.startswith("worker:"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Worker authentication required",
        )

    worker_id = int(token.sub.split(":")[1])
    worker = session.get(Worker, worker_id)

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worker not found",
        )

    if worker.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Worker is banned",
        )

    return worker


async def require_admin(
    token: TokenData = Depends(require_auth),
) -> TokenData:
    """Require admin authentication."""
    if not token.sub.startswith("admin:"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return token


def optional_auth(
    token: Optional[TokenData] = Depends(get_current_token),
) -> Optional[TokenData]:
    """Optional authentication - returns None if no valid token."""
    return token


# =============================================================================
# AUTH SCHEMAS
# =============================================================================

class WorkerAuthRequest(BaseModel):
    """Request for worker authentication."""
    worker_id: int
    api_key: str


class WorkerAuthResponse(BaseModel):
    """Response after successful worker authentication."""
    access_token: str
    token_type: str = "bearer"
    worker_id: int
    expires_in: int


class AdminLoginRequest(BaseModel):
    """Request for admin login."""
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    """Response after successful admin login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str
