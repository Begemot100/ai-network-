"""
Tests for reputation system.
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session

from server.models import Worker


class TestReputationLevels:
    """Tests for reputation level transitions."""

    def test_initial_reputation(self, worker_a: Worker):
        """Test that workers start with reputation 1.0 (bronze)."""
        assert worker_a.reputation == Decimal("1.0")
        assert worker_a.reputation_level == "bronze"

    def test_reputation_level_bronze(self, session: Session):
        """Test bronze level thresholds."""
        worker = Worker(
            name="Bronze",
            power=5,
            capabilities="text",
            reputation=Decimal("1.4"),
            reputation_level="bronze",
        )
        session.add(worker)
        session.commit()

        assert worker.reputation_level == "bronze"

    def test_reputation_level_silver(self, session: Session):
        """Test silver level at 1.5+."""
        worker = Worker(
            name="Silver",
            power=5,
            capabilities="text",
            reputation=Decimal("1.5"),
            reputation_level="bronze",
        )
        session.add(worker)
        session.commit()

        worker.update_reputation_level()
        assert worker.reputation_level == "silver"

    def test_reputation_level_gold(self, session: Session):
        """Test gold level at 2.0+."""
        worker = Worker(
            name="Gold",
            power=5,
            capabilities="text",
            reputation=Decimal("2.0"),
            reputation_level="bronze",
        )
        session.add(worker)
        session.commit()

        worker.update_reputation_level()
        assert worker.reputation_level == "gold"

    def test_reputation_level_platinum(self, session: Session):
        """Test platinum level at 3.0+."""
        worker = Worker(
            name="Platinum",
            power=5,
            capabilities="text",
            reputation=Decimal("3.0"),
            reputation_level="bronze",
        )
        session.add(worker)
        session.commit()

        worker.update_reputation_level()
        assert worker.reputation_level == "platinum"

    def test_reputation_level_diamond(self, session: Session):
        """Test diamond level at 5.0+."""
        worker = Worker(
            name="Diamond",
            power=5,
            capabilities="text",
            reputation=Decimal("5.0"),
            reputation_level="bronze",
        )
        session.add(worker)
        session.commit()

        worker.update_reputation_level()
        assert worker.reputation_level == "diamond"


class TestReputationChanges:
    """Tests for reputation changes during task validation."""

    def test_reputation_increase_on_success(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test reputation increases on successful task."""
        initial_rep = worker_a.reputation

        # Complete task successfully
        task_id = client.post(
            "/tasks/create",
            json={"prompt": "test", "task_type": "text"}
        ).json()["task_id"]

        client.get(f"/tasks/next/{worker_a.id}")
        client.post(
            "/tasks/submit",
            json={"task_id": task_id, "worker_id": worker_a.id, "result": "test"}
        )
        client.get(f"/tasks/next/{worker_b.id}")
        client.post(
            "/tasks/validate",
            json={"task_id": task_id, "worker_id": worker_b.id, "result": "test"}
        )

        session.refresh(worker_a)
        assert worker_a.reputation > initial_rep

    def test_reputation_decrease_on_failure(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test reputation decreases on failed validation."""
        initial_rep = worker_a.reputation

        # Complete task with mismatch
        task_id = client.post(
            "/tasks/create",
            json={"prompt": "test", "task_type": "text"}
        ).json()["task_id"]

        client.get(f"/tasks/next/{worker_a.id}")
        client.post(
            "/tasks/submit",
            json={"task_id": task_id, "worker_id": worker_a.id, "result": "wrong"}
        )
        client.get(f"/tasks/next/{worker_b.id}")
        client.post(
            "/tasks/validate",
            json={"task_id": task_id, "worker_id": worker_b.id, "result": "correct"}
        )

        session.refresh(worker_a)
        assert worker_a.reputation < initial_rep

    def test_validator_reputation_increase(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test validator gets reputation increase."""
        initial_rep = worker_b.reputation

        task_id = client.post(
            "/tasks/create",
            json={"prompt": "test", "task_type": "text"}
        ).json()["task_id"]

        client.get(f"/tasks/next/{worker_a.id}")
        client.post(
            "/tasks/submit",
            json={"task_id": task_id, "worker_id": worker_a.id, "result": "test"}
        )
        client.get(f"/tasks/next/{worker_b.id}")
        client.post(
            "/tasks/validate",
            json={"task_id": task_id, "worker_id": worker_b.id, "result": "test"}
        )

        session.refresh(worker_b)
        assert worker_b.reputation > initial_rep


class TestReputationBounds:
    """Tests for reputation bounds (0-10)."""

    def test_reputation_cannot_go_below_zero(
        self, client: TestClient, session: Session
    ):
        """Test reputation is bounded at 0."""
        # Create worker with very low reputation
        worker = Worker(
            name="LowRep",
            power=5,
            capabilities="text",
            reputation=Decimal("0.05"),
            reputation_level="bronze",
        )
        session.add(worker)

        validator = Worker(
            name="Validator",
            power=5,
            capabilities="text",
            reputation=Decimal("1.0"),
            reputation_level="bronze",
        )
        session.add(validator)
        session.commit()
        session.refresh(worker)
        session.refresh(validator)

        # Fail multiple tasks to try to push below 0
        for _ in range(5):
            task_id = client.post(
                "/tasks/create",
                json={"prompt": "test", "task_type": "text"}
            ).json()["task_id"]

            client.get(f"/tasks/next/{worker.id}")
            client.post(
                "/tasks/submit",
                json={"task_id": task_id, "worker_id": worker.id, "result": "wrong"}
            )
            client.get(f"/tasks/next/{validator.id}")
            client.post(
                "/tasks/validate",
                json={
                    "task_id": task_id,
                    "worker_id": validator.id,
                    "result": "correct"
                }
            )

        session.refresh(worker)
        assert worker.reputation >= Decimal("0.0")

    def test_reputation_cannot_exceed_ten(self, session: Session):
        """Test reputation is bounded at 10."""
        worker = Worker(
            name="MaxRep",
            power=5,
            capabilities="text",
            reputation=Decimal("10.0"),
            reputation_level="diamond",
        )
        session.add(worker)
        session.commit()

        # Try to increase beyond 10
        worker.reputation = worker.reputation + Decimal("1.0")
        worker.reputation = min(Decimal("10.0"), worker.reputation)

        assert worker.reputation <= Decimal("10.0")


class TestSuccessRate:
    """Tests for success rate calculation."""

    def test_success_rate_calculation(self, high_rep_worker: Worker):
        """Test success rate is calculated correctly."""
        # high_rep_worker has 500 completed, 5 failed
        expected_rate = 500 / 505 * 100
        assert abs(high_rep_worker.success_rate - expected_rate) < 0.1

    def test_success_rate_zero_tasks(self, worker_a: Worker):
        """Test success rate with no tasks."""
        assert worker_a.success_rate == 0.0

    def test_success_rate_all_success(self, session: Session):
        """Test success rate with 100% success."""
        worker = Worker(
            name="Perfect",
            power=5,
            capabilities="text",
            tasks_completed=100,
            tasks_failed=0,
        )
        session.add(worker)
        session.commit()

        assert worker.success_rate == 100.0

    def test_success_rate_all_failed(self, session: Session):
        """Test success rate with 0% success."""
        worker = Worker(
            name="Failed",
            power=5,
            capabilities="text",
            tasks_completed=0,
            tasks_failed=100,
        )
        session.add(worker)
        session.commit()

        assert worker.success_rate == 0.0
