"""
Tests for transaction and wallet functionality.
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session

from server.models import Worker, Transaction, WithdrawalRequest


class TestTransactionCreation:
    """Tests for transaction creation during task completion."""

    def test_transaction_created_on_reward(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test that transactions are created when workers are rewarded."""
        # Complete a task
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

        # Check Worker A has transactions
        response = client.get(f"/workers/{worker_a.id}/transactions")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        assert any(t["type"] == "reward" for t in data["transactions"])

    def test_transaction_tracks_balance_changes(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test that transactions correctly track balance before/after."""
        # Initial balance
        session.refresh(worker_a)
        assert worker_a.balance == Decimal("0.0")

        # Complete a task
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

        # Verify transaction
        response = client.get(f"/workers/{worker_a.id}/transactions")
        tx = response.json()["transactions"][0]

        assert Decimal(str(tx["balance_before"])) == Decimal("0.0")
        assert Decimal(str(tx["balance_after"])) > Decimal("0.0")
        assert Decimal(str(tx["amount"])) == Decimal(str(tx["balance_after"]))

    def test_bonus_transaction_on_mismatch_catch(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test bonus transaction when validator catches mismatch."""
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

        # Worker B should have bonus transaction
        response = client.get(f"/workers/{worker_b.id}/transactions")
        data = response.json()
        assert any(t["type"] == "bonus" for t in data["transactions"])


class TestTransactionHistory:
    """Tests for transaction history retrieval."""

    def test_transaction_pagination(
        self, client: TestClient, session: Session, worker_a: Worker
    ):
        """Test transaction history pagination."""
        # Create multiple transactions
        for i in range(15):
            tx = Transaction(
                worker_id=worker_a.id,
                type="reward",
                amount=Decimal("0.05"),
                balance_before=Decimal(str(i * 0.05)),
                balance_after=Decimal(str((i + 1) * 0.05)),
                description=f"Test transaction {i}",
            )
            session.add(tx)
        session.commit()

        # Get first page
        response = client.get(
            f"/workers/{worker_a.id}/transactions?page=1&page_size=10"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["transactions"]) == 10
        assert data["total"] == 15

        # Get second page
        response = client.get(
            f"/workers/{worker_a.id}/transactions?page=2&page_size=10"
        )
        data = response.json()
        assert len(data["transactions"]) == 5

    def test_transaction_order(
        self, client: TestClient, session: Session, worker_a: Worker
    ):
        """Test that transactions are ordered newest first."""
        # Create transactions with sequential amounts for identification
        for i in range(5):
            tx = Transaction(
                worker_id=worker_a.id,
                type="reward",
                amount=Decimal(str(i + 1)),
                balance_before=Decimal("0"),
                balance_after=Decimal(str(i + 1)),
                description=f"Transaction {i}",
            )
            session.add(tx)
        session.commit()

        response = client.get(f"/workers/{worker_a.id}/transactions")
        transactions = response.json()["transactions"]

        # Newest (amount=5) should be first
        assert transactions[0]["amount"] == 5.0


class TestReputationHistory:
    """Tests for reputation history tracking."""

    def test_reputation_history_on_success(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test reputation history logged on successful task."""
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

        # Check reputation history
        response = client.get(f"/workers/{worker_a.id}/reputation/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) > 0
        assert data["history"][0]["change_amount"] > 0

    def test_reputation_history_on_failure(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test reputation history logged on failed task."""
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

        # Check negative reputation change
        response = client.get(f"/workers/{worker_a.id}/reputation/history")
        data = response.json()
        assert any(h["change_amount"] < 0 for h in data["history"])


class TestTotalEarned:
    """Tests for total earned tracking."""

    def test_total_earned_increases(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test that total_earned increases on rewards."""
        session.refresh(worker_a)
        initial_earned = worker_a.total_earned

        # Complete multiple tasks
        for _ in range(3):
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
        assert worker_a.total_earned > initial_earned
