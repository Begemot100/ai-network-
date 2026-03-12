"""
Tests for worker management endpoints.
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlmodel import Session

from server.models import Worker, WorkerStatus


class TestWorkerRegistration:
    """Tests for worker registration."""

    def test_register_worker_success(self, client: TestClient):
        """Test successful worker registration."""
        response = client.post(
            "/workers/register",
            json={"name": "New-Worker", "power": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert "worker_id" in data
        assert "uuid" in data
        assert data["reputation"] == 1.0
        assert data["status"] == "registered"

    def test_register_worker_with_capabilities(self, client: TestClient):
        """Test worker registration with capabilities."""
        response = client.post(
            "/workers/register",
            json={
                "name": "GPU-Worker",
                "power": 50,
                "capabilities": "text,llm,heavy",
                "fingerprint": "abc123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] > 0

    def test_register_worker_invalid_power(self, client: TestClient):
        """Test registration with invalid power value."""
        response = client.post(
            "/workers/register",
            json={"name": "Invalid", "power": 200}
        )

        assert response.status_code == 422

    def test_register_worker_empty_name(self, client: TestClient):
        """Test registration with empty name."""
        response = client.post(
            "/workers/register",
            json={"name": "", "power": 5}
        )

        assert response.status_code == 422


class TestWorkerInfo:
    """Tests for worker information retrieval."""

    def test_get_worker_by_id(self, client: TestClient, worker_a: Worker):
        """Test getting worker by ID."""
        response = client.get(f"/workers/{worker_a.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == worker_a.id
        assert data["name"] == "Worker-A"
        assert data["power"] == 10

    def test_get_worker_not_found(self, client: TestClient):
        """Test getting non-existent worker."""
        response = client.get("/workers/99999")

        assert response.status_code == 404

    def test_get_worker_by_uuid(self, client: TestClient, worker_a: Worker):
        """Test getting worker by UUID."""
        response = client.get(f"/workers/uuid/{worker_a.uuid}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == worker_a.id

    def test_worker_success_rate(self, client: TestClient, high_rep_worker: Worker):
        """Test worker success rate calculation."""
        response = client.get(f"/workers/{high_rep_worker.id}")

        assert response.status_code == 200
        data = response.json()
        # 500 completed / (500 + 5) total * 100 ≈ 99.01%
        assert data["success_rate"] > 98


class TestWorkerList:
    """Tests for worker listing."""

    def test_list_workers(self, client: TestClient, worker_a: Worker, worker_b: Worker):
        """Test listing workers."""
        response = client.get("/workers/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2
        assert len(data["workers"]) >= 2

    def test_list_workers_pagination(self, client: TestClient, session: Session):
        """Test pagination of worker list."""
        # Create multiple workers
        for i in range(15):
            worker = Worker(
                name=f"Worker-{i}",
                power=5,
                capabilities="text",
                balance=Decimal("0.0"),
                reputation=Decimal("1.0"),
                reputation_level="bronze",
                status=WorkerStatus.IDLE.value,
            )
            session.add(worker)
        session.commit()

        # Get first page
        response = client.get("/workers/?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["workers"]) == 10
        assert data["page"] == 1

        # Get second page
        response = client.get("/workers/?page=2&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["workers"]) >= 5
        assert data["page"] == 2

    def test_list_workers_exclude_banned(
        self, client: TestClient, worker_a: Worker, banned_worker: Worker
    ):
        """Test that banned workers are excluded by default."""
        response = client.get("/workers/")

        assert response.status_code == 200
        data = response.json()
        worker_ids = [w["id"] for w in data["workers"]]
        assert banned_worker.id not in worker_ids

    def test_list_workers_include_banned(
        self, client: TestClient, worker_a: Worker, banned_worker: Worker
    ):
        """Test including banned workers."""
        response = client.get("/workers/?include_banned=true")

        assert response.status_code == 200
        data = response.json()
        worker_ids = [w["id"] for w in data["workers"]]
        assert banned_worker.id in worker_ids

    def test_list_workers_filter_by_status(
        self, client: TestClient, worker_a: Worker, high_rep_worker: Worker
    ):
        """Test filtering workers by status."""
        response = client.get("/workers/?status=online")

        assert response.status_code == 200
        data = response.json()
        for worker in data["workers"]:
            assert worker["status"] == "online"


class TestWorkerHeartbeat:
    """Tests for worker heartbeat."""

    def test_heartbeat_success(self, client: TestClient, worker_a: Worker):
        """Test successful heartbeat."""
        response = client.post(f"/workers/heartbeat?worker_id={worker_a.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_heartbeat_updates_status(
        self, client: TestClient, session: Session, worker_a: Worker
    ):
        """Test that heartbeat updates worker status."""
        # Worker should change to online after heartbeat
        response = client.post(f"/workers/heartbeat?worker_id={worker_a.id}")
        assert response.status_code == 200

        session.refresh(worker_a)
        assert worker_a.status == WorkerStatus.ONLINE.value

    def test_heartbeat_banned_worker(self, client: TestClient, banned_worker: Worker):
        """Test heartbeat from banned worker."""
        response = client.post(f"/workers/heartbeat?worker_id={banned_worker.id}")

        assert response.status_code == 403

    def test_heartbeat_nonexistent_worker(self, client: TestClient):
        """Test heartbeat from non-existent worker."""
        response = client.post("/workers/heartbeat?worker_id=99999")

        assert response.status_code == 404


class TestWorkerStatus:
    """Tests for worker status updates."""

    def test_update_status(self, client: TestClient, worker_a: Worker):
        """Test updating worker status."""
        response = client.post(f"/workers/status/{worker_a.id}?status=working")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_update_status_invalid(self, client: TestClient, worker_a: Worker):
        """Test updating with invalid status."""
        response = client.post(f"/workers/status/{worker_a.id}?status=invalid_status")

        assert response.status_code == 400

    def test_update_status_banned_worker(self, client: TestClient, banned_worker: Worker):
        """Test updating banned worker status."""
        response = client.post(f"/workers/status/{banned_worker.id}?status=online")

        assert response.status_code == 403


class TestWorkerStatistics:
    """Tests for worker statistics."""

    def test_get_worker_stats(
        self, client: TestClient, worker_a: Worker, worker_b: Worker
    ):
        """Test getting worker statistics."""
        response = client.get("/workers/stats/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total_workers"] >= 2
        assert "active_workers" in data
        assert "banned_workers" in data
        assert "avg_reputation" in data


class TestWorkerLeaderboard:
    """Tests for worker leaderboards."""

    def test_reputation_leaderboard(
        self, client: TestClient, worker_a: Worker, high_rep_worker: Worker
    ):
        """Test reputation leaderboard."""
        response = client.get("/workers/leaderboard/reputation")

        assert response.status_code == 200
        data = response.json()
        assert len(data["leaderboard"]) > 0
        # High rep worker should be first
        assert data["leaderboard"][0]["worker_id"] == high_rep_worker.id

    def test_earnings_leaderboard(
        self, client: TestClient, worker_a: Worker, high_rep_worker: Worker
    ):
        """Test earnings leaderboard."""
        response = client.get("/workers/leaderboard/earnings")

        assert response.status_code == 200
        data = response.json()
        assert len(data["leaderboard"]) > 0


class TestWorkerTransactions:
    """Tests for worker transaction history."""

    def test_get_worker_transactions_empty(self, client: TestClient, worker_a: Worker):
        """Test getting empty transaction history."""
        response = client.get(f"/workers/{worker_a.id}/transactions")

        assert response.status_code == 200
        data = response.json()
        assert data["transactions"] == []
        assert data["total"] == 0

    def test_get_worker_transactions_not_found(self, client: TestClient):
        """Test getting transactions for non-existent worker."""
        response = client.get("/workers/99999/transactions")

        assert response.status_code == 404
