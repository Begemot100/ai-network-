"""
Authentication endpoints for the Distributed AI Network.
Handles worker and admin authentication.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlmodel import Session, select

from ..db import get_session
from ..config import settings
from ..models import Worker, AuditLog, AuditAction
from ..auth import (
    create_access_token,
    create_refresh_token,
    create_worker_token,
    decode_token,
    hash_api_key,
    hash_password,
    verify_password,
    generate_api_key,
    WorkerAuthRequest,
    WorkerAuthResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    RefreshTokenRequest,
    TokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# =============================================================================
# ADMIN CREDENTIALS (in production, use database or external auth)
# =============================================================================

# Simple in-memory admin store for development
# In production, replace with database-backed admin model
_admin_users_cache = None

def get_admin_users():
    """Lazy initialization of admin users."""
    global _admin_users_cache
    if _admin_users_cache is None:
        _admin_users_cache = {
            "admin": hash_password("admin123"),  # Change in production!
        }
    return _admin_users_cache


# =============================================================================
# WORKER AUTHENTICATION
# =============================================================================

@router.post("/worker/register", response_model=dict)
def register_worker_with_auth(
    name: str,
    power: int = 5,
    capabilities: str = "text",
    request: Request = None,
    session: Session = Depends(get_session),
):
    """
    Register a new worker and return authentication credentials.

    Returns:
        - worker_id: The worker's ID
        - api_key: Secret API key for authentication (store securely!)
        - token: JWT token for immediate use
    """
    # Generate API key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    # Create worker
    worker = Worker(
        name=name,
        power=power,
        capabilities=capabilities,
        fingerprint=api_key_hash,  # Store hashed API key in fingerprint field
        status="idle",
        reputation_level="bronze",
    )

    session.add(worker)
    session.flush()

    # Create token
    token = create_worker_token(worker.id)

    # Audit log
    audit = AuditLog(
        action=AuditAction.WORKER_REGISTER.value,
        actor_type="worker",
        actor_id=worker.id,
        target_type="worker",
        target_id=worker.id,
        details={
            "name": name,
            "power": power,
            "capabilities": capabilities,
            "authenticated": True,
        },
        ip_address=request.client.host if request else None,
    )
    session.add(audit)
    session.commit()

    logger.info(f"Worker registered with auth: id={worker.id}, name={name}")

    return {
        "worker_id": worker.id,
        "uuid": worker.uuid,
        "api_key": api_key,  # Only returned once!
        "token": token,
        "expires_in": 365 * 24 * 3600,  # 1 year in seconds
        "message": "Store the api_key securely - it cannot be retrieved again!",
    }


@router.post("/worker/token", response_model=WorkerAuthResponse)
def authenticate_worker(
    data: WorkerAuthRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Authenticate a worker using API key and get access token.
    """
    worker = session.get(Worker, data.worker_id)

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if worker.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Worker is banned",
        )

    # Verify API key
    api_key_hash = hash_api_key(data.api_key)
    if worker.fingerprint != api_key_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Create token
    token = create_worker_token(worker.id)

    # Update last seen
    worker.last_seen = datetime.now(timezone.utc)
    session.add(worker)
    session.commit()

    logger.info(f"Worker authenticated: id={worker.id}")

    return WorkerAuthResponse(
        access_token=token,
        worker_id=worker.id,
        expires_in=365 * 24 * 3600,
    )


# =============================================================================
# ADMIN AUTHENTICATION
# =============================================================================

@router.post("/admin/login", response_model=AdminLoginResponse)
def admin_login(
    data: AdminLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Admin login endpoint.
    """
    # Check credentials
    admin_users = get_admin_users()
    if data.username not in admin_users:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(data.password, admin_users[data.username]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Create tokens
    access_token = create_access_token(f"admin:{data.username}")
    refresh_token = create_refresh_token(f"admin:{data.username}")

    # Audit log
    audit = AuditLog(
        action="admin_login",
        actor_type="admin",
        actor_id=None,
        target_type=None,
        target_id=None,
        details={"username": data.username},
        ip_address=request.client.host if request else None,
    )
    session.add(audit)
    session.commit()

    logger.info(f"Admin logged in: {data.username}")

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expiry_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    data: RefreshTokenRequest,
    session: Session = Depends(get_session),
):
    """
    Refresh an access token using a refresh token.
    """
    # Decode refresh token
    token_data = decode_token(data.refresh_token)

    if token_data.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token type - expected refresh token",
        )

    # Create new tokens
    access_token = create_access_token(token_data.sub)
    refresh_token = create_refresh_token(token_data.sub)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expiry_minutes * 60,
    )


@router.post("/verify")
def verify_token(
    token: str,
):
    """
    Verify a token and return its payload.
    """
    token_data = decode_token(token)

    return {
        "valid": True,
        "subject": token_data.sub,
        "type": token_data.type,
        "expires_at": token_data.exp.isoformat(),
        "issued_at": token_data.iat.isoformat(),
    }


# =============================================================================
# API KEY ROTATION
# =============================================================================

@router.post("/worker/rotate-key", response_model=dict)
def rotate_worker_api_key(
    data: WorkerAuthRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Rotate a worker's API key.
    Requires current API key for authentication.
    """
    worker = session.get(Worker, data.worker_id)

    if not worker:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Verify current API key
    api_key_hash = hash_api_key(data.api_key)
    if worker.fingerprint != api_key_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Generate new API key
    new_api_key = generate_api_key()
    new_api_key_hash = hash_api_key(new_api_key)

    worker.fingerprint = new_api_key_hash
    worker.updated_at = datetime.now(timezone.utc)

    # Audit log
    audit = AuditLog(
        action="worker_key_rotation",
        actor_type="worker",
        actor_id=worker.id,
        target_type="worker",
        target_id=worker.id,
        details={"rotated": True},
        ip_address=request.client.host if request else None,
    )
    session.add(audit)
    session.commit()

    # Create new token
    token = create_worker_token(worker.id)

    logger.info(f"Worker API key rotated: id={worker.id}")

    return {
        "worker_id": worker.id,
        "new_api_key": new_api_key,
        "token": token,
        "message": "Old API key is now invalid. Store the new key securely!",
    }
