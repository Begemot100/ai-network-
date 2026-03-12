"""
Pytest configuration and fixtures for the Distributed AI Network tests.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

# Import models and app
import sys
sys.path.insert(0, "/home/greg/my-ai-network")

from server.main import app
from server.db import get_session
from server.models import (
    Worker, Task, Transaction, GoldenTask,
    ReputationHistory, AuditLog, WorkerStatus
)


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest.fixture(name="engine")
def engine_fixture():
    """Create in-memory SQLite engine for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine) -> Generator[Session, None, None]:
    """Create database session for tests."""
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    """Create test client with overridden session dependency."""

    def get_session_override():
        yield session

    app.dependency_overrides[get_session] = get_session_override

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# WORKER FIXTURES
# =============================================================================

@pytest.fixture
def worker_a(session: Session) -> Worker:
    """Create Worker A for testing."""
    worker = Worker(
        name="Worker-A",
        power=10,
        capabilities="text,reverse,math",
        balance=Decimal("0.0"),
        reputation=Decimal("1.0"),
        reputation_level="bronze",
        status=WorkerStatus.IDLE.value,
    )
    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


@pytest.fixture
def worker_b(session: Session) -> Worker:
    """Create Worker B for testing."""
    worker = Worker(
        name="Worker-B",
        power=8,
        capabilities="text,reverse",
        balance=Decimal("0.0"),
        reputation=Decimal("1.0"),
        reputation_level="bronze",
        status=WorkerStatus.IDLE.value,
    )
    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


@pytest.fixture
def high_rep_worker(session: Session) -> Worker:
    """Create high reputation worker for testing."""
    worker = Worker(
        name="Diamond-Worker",
        power=50,
        capabilities="text,reverse,math,llm,heavy",
        balance=Decimal("100.0"),
        reputation=Decimal("5.5"),
        reputation_level="diamond",
        status=WorkerStatus.ONLINE.value,
        tasks_completed=500,
        tasks_failed=5,
    )
    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


@pytest.fixture
def banned_worker(session: Session) -> Worker:
    """Create banned worker for testing."""
    worker = Worker(
        name="Banned-Worker",
        power=5,
        capabilities="text",
        balance=Decimal("10.0"),
        reputation=Decimal("0.5"),
        reputation_level="bronze",
        status=WorkerStatus.BANNED.value,
        is_banned=True,
        ban_reason="Fraud detected",
        banned_at=datetime.now(timezone.utc),
    )
    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


# =============================================================================
# TASK FIXTURES
# =============================================================================

@pytest.fixture
def pending_task(session: Session) -> Task:
    """Create pending task for testing."""
    task = Task(
        prompt="reverse:hello",
        task_type="reverse",
        status="pending",
        priority=0,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@pytest.fixture
def assigned_task(session: Session, worker_a: Worker) -> Task:
    """Create assigned task for testing."""
    task = Task(
        prompt="reverse:world",
        task_type="reverse",
        status="assigned",
        worker_id=worker_a.id,
        priority=0,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@pytest.fixture
def submitted_task(session: Session, worker_a: Worker) -> Task:
    """Create submitted task awaiting validation."""
    task = Task(
        prompt="reverse:test",
        task_type="reverse",
        status="submitted_A",
        worker_id=worker_a.id,
        result="tset",
        result_hash="abc123",
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@pytest.fixture
def golden_task(session: Session) -> GoldenTask:
    """Create golden task (honeypot) for testing."""
    golden = GoldenTask(
        prompt="reverse:golden",
        task_type="reverse",
        expected_answer="nedlog",
        is_active=True,
    )
    session.add(golden)
    session.commit()
    session.refresh(golden)
    return golden


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_worker(session: Session, name: str = "Test-Worker", **kwargs) -> Worker:
    """Helper to create a worker with custom attributes."""
    defaults = {
        "power": 5,
        "capabilities": "text",
        "balance": Decimal("0.0"),
        "reputation": Decimal("1.0"),
        "reputation_level": "bronze",
        "status": WorkerStatus.IDLE.value,
    }
    defaults.update(kwargs)

    worker = Worker(name=name, **defaults)
    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


def create_task(session: Session, prompt: str = "test", **kwargs) -> Task:
    """Helper to create a task with custom attributes."""
    defaults = {
        "task_type": "text",
        "status": "pending",
        "priority": 0,
    }
    defaults.update(kwargs)

    task = Task(prompt=prompt, **defaults)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task
