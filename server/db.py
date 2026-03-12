"""
Database connection and session management for the Distributed AI Network.
Uses SQLModel with connection pooling for production workloads.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import QueuePool
from sqlalchemy import event, text

from .config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# ENGINE CONFIGURATION
# =============================================================================

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # Enable connection health checks
    poolclass=QueuePool,
    connect_args={
        "application_name": "ai-network-main-server",
        "connect_timeout": 10,
    }
)


# =============================================================================
# CONNECTION EVENTS
# =============================================================================

@event.listens_for(engine, "connect")
def set_search_path(dbapi_connection, connection_record):
    """Set default search path on new connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET search_path TO public")
    cursor.close()


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log connection checkout from pool."""
    logger.debug("Connection checked out from pool")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Log connection return to pool."""
    logger.debug("Connection returned to pool")


# =============================================================================
# SESSION MANAGEMENT
# =============================================================================

def get_session() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database sessions.
    Ensures proper cleanup after request completion.
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for getting database sessions outside of FastAPI.
    Use this in background tasks, workers, etc.
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =============================================================================
# INITIALIZATION
# =============================================================================

def init_db() -> None:
    """
    Initialize database tables.
    In production, use Alembic migrations instead.
    """
    logger.info("Initializing database...")

    # Import all models to register them
    from . import models  # noqa: F401

    # Create tables (only for development)
    if settings.dev_mode:
        SQLModel.metadata.create_all(engine)
        logger.info("Database tables created (dev mode)")
    else:
        logger.info("Skipping table creation (use migrations in production)")


def check_db_connection() -> bool:
    """
    Check if database connection is healthy.
    Used for health checks.
    """
    try:
        with Session(engine) as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


def get_db_stats() -> dict:
    """Get database connection pool statistics."""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalidatedcount() if hasattr(pool, 'invalidatedcount') else 0,
    }
