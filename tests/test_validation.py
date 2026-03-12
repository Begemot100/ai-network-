"""
Tests for two-tier validation system.
This is the core logic of the distributed AI network.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session

from server.models import Worker, Task, Transaction, GoldenTask


class TestTaskCreation:
    """Tests for task creation."""

    def test_create_task(self, client: TestClient):
        """Test creating a new task."""
        response = client.post(
            "/tasks/create",
            json={"prompt": "reverse:hello", "task_type": "reverse"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "created"

    def test_create_task_with_priority(self, client: TestClient):
        """Test creating task with priority."""
        response = client.post(
            "/tasks/create",
            json={"prompt": "math:2+2", "task_type": "math", "priority": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_create_task_default_type(self, client: TestClient):
        """Test that default task type is 'text'."""
        response = client.post(
            "/tasks/create",
            json={"prompt": "hello"}
        )

        assert response.status_code == 200


class TestTaskAssignment:
    """Tests for task assignment (Worker A gets task)."""

    def test_get_next_task(
        self, client: TestClient, worker_a: Worker, pending_task: Task
    ):
        """Test worker getting next task."""
        response = client.get(f"/tasks/next/{worker_a.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == pending_task.id
        assert data["mode"] == "work"
        assert data["prompt"] == pending_task.prompt

    def test_get_next_task_no_tasks(self, client: TestClient, worker_a: Worker):
        """Test when no tasks are available."""
        response = client.get(f"/tasks/next/{worker_a.id}")

        assert response.status_code == 200
        data = response.json()
        assert data.get("task") is None

    def test_get_next_task_banned_worker(
        self, client: TestClient, banned_worker: Worker, pending_task: Task
    ):
        """Test banned worker cannot get tasks."""
        response = client.get(f"/tasks/next/{banned_worker.id}")

        assert response.status_code == 403

    def test_get_next_task_nonexistent_worker(
        self, client: TestClient, pending_task: Task
    ):
        """Test non-existent worker cannot get tasks."""
        response = client.get("/tasks/next/99999")

        assert response.status_code == 404

    def test_validation_task_priority(
        self, client: TestClient, worker_a: Worker, worker_b: Worker,
        submitted_task: Task, pending_task: Task
    ):
        """Test that validation tasks have priority over new tasks."""
        # Worker B should get validation task, not pending task
        response = client.get(f"/tasks/next/{worker_b.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == submitted_task.id
        assert data["mode"] == "validate"


class TestResultSubmission:
    """Tests for Worker A result submission."""

    def test_submit_result(
        self, client: TestClient, session: Session,
        worker_a: Worker, assigned_task: Task
    ):
        """Test successful result submission."""
        response = client.post(
            "/tasks/submit",
            json={
                "task_id": assigned_task.id,
                "worker_id": worker_a.id,
                "result": "dlrow"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["stage"] == "awaiting_validation"

        # Check task state updated
        session.refresh(assigned_task)
        assert assigned_task.status == "submitted_A"
        assert assigned_task.result == "dlrow"
        assert assigned_task.result_hash is not None

    def test_submit_result_wrong_worker(
        self, client: TestClient, worker_b: Worker, assigned_task: Task
    ):
        """Test submission by wrong worker."""
        response = client.post(
            "/tasks/submit",
            json={
                "task_id": assigned_task.id,
                "worker_id": worker_b.id,
                "result": "dlrow"
            }
        )

        assert response.status_code == 403

    def test_submit_result_invalid_status(
        self, client: TestClient, worker_a: Worker, pending_task: Task
    ):
        """Test submission for non-assigned task."""
        response = client.post(
            "/tasks/submit",
            json={
                "task_id": pending_task.id,
                "worker_id": worker_a.id,
                "result": "olleh"
            }
        )

        assert response.status_code == 400

    def test_submit_result_task_not_found(self, client: TestClient, worker_a: Worker):
        """Test submission for non-existent task."""
        response = client.post(
            "/tasks/submit",
            json={
                "task_id": 99999,
                "worker_id": worker_a.id,
                "result": "test"
            }
        )

        assert response.status_code == 404


class TestValidation:
    """Tests for Worker B validation (core logic)."""

    def test_validation_match(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test validation when results match - both workers rewarded."""
        # Create and assign task to Worker A
        response = client.post(
            "/tasks/create",
            json={"prompt": "reverse:hello", "task_type": "reverse"}
        )
        task_id = response.json()["task_id"]

        # Worker A gets task
        response = client.get(f"/tasks/next/{worker_a.id}")
        assert response.json()["mode"] == "work"

        # Worker A submits result
        client.post(
            "/tasks/submit",
            json={"task_id": task_id, "worker_id": worker_a.id, "result": "olleh"}
        )

        # Worker B gets validation task
        response = client.get(f"/tasks/next/{worker_b.id}")
        assert response.json()["mode"] == "validate"

        # Store initial balances
        session.refresh(worker_a)
        session.refresh(worker_b)
        initial_balance_a = worker_a.balance
        initial_balance_b = worker_b.balance

        # Worker B validates with matching result
        response = client.post(
            "/tasks/validate",
            json={"task_id": task_id, "worker_id": worker_b.id, "result": "olleh"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["validation"] == "done"

        # Check rewards
        session.refresh(worker_a)
        session.refresh(worker_b)
        assert worker_a.balance > initial_balance_a
        assert worker_b.balance > initial_balance_b
        assert worker_a.tasks_completed == 1
        assert worker_b.validations_completed == 1

    def test_validation_mismatch(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test validation when results don't match."""
        # Create and assign task
        response = client.post(
            "/tasks/create",
            json={"prompt": "reverse:hello", "task_type": "reverse"}
        )
        task_id = response.json()["task_id"]

        # Worker A gets and submits (wrong result)
        client.get(f"/tasks/next/{worker_a.id}")
        client.post(
            "/tasks/submit",
            json={"task_id": task_id, "worker_id": worker_a.id, "result": "wrong"}
        )

        # Worker B validates
        client.get(f"/tasks/next/{worker_b.id}")

        session.refresh(worker_a)
        initial_rep_a = worker_a.reputation

        response = client.post(
            "/tasks/validate",
            json={"task_id": task_id, "worker_id": worker_b.id, "result": "olleh"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["validation"] == "rejected"

        # Check reputation penalty for Worker A
        session.refresh(worker_a)
        assert worker_a.reputation < initial_rep_a
        assert worker_a.tasks_failed == 1

        # Worker B should get bonus for catching mismatch
        session.refresh(worker_b)
        assert worker_b.balance > 0

    def test_validation_wrong_validator(
        self, client: TestClient, worker_a: Worker, submitted_task: Task
    ):
        """Test that only assigned validator can validate."""
        # Try to validate with wrong worker
        response = client.post(
            "/tasks/validate",
            json={
                "task_id": submitted_task.id,
                "worker_id": worker_a.id,  # Worker A is executor, not validator
                "result": "tset"
            }
        )

        # Should fail because task is in submitted_A state, not validating
        assert response.status_code == 400

    def test_validation_invalid_status(
        self, client: TestClient, worker_b: Worker, pending_task: Task
    ):
        """Test validation for task in wrong status."""
        response = client.post(
            "/tasks/validate",
            json={
                "task_id": pending_task.id,
                "worker_id": worker_b.id,
                "result": "test"
            }
        )

        assert response.status_code == 400


class TestGoldenTasks:
    """Tests for golden task (honeypot) system."""

    def test_golden_task_pass(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker, golden_task: GoldenTask
    ):
        """Test passing a golden task."""
        # Create task (may inject golden task)
        # For deterministic testing, we create task directly
        task = Task(
            prompt=golden_task.prompt,
            task_type=golden_task.task_type,
            status="pending",
            is_golden=True,
            golden_answer=golden_task.expected_answer,
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        # Worker A gets and submits correct answer
        client.get(f"/tasks/next/{worker_a.id}")
        session.refresh(task)  # Refresh to get updated status

        client.post(
            "/tasks/submit",
            json={
                "task_id": task.id,
                "worker_id": worker_a.id,
                "result": golden_task.expected_answer
            }
        )

        # Worker B validates
        client.get(f"/tasks/next/{worker_b.id}")
        response = client.post(
            "/tasks/validate",
            json={
                "task_id": task.id,
                "worker_id": worker_b.id,
                "result": golden_task.expected_answer
            }
        )

        assert response.status_code == 200
        session.refresh(worker_a)
        assert worker_a.golden_tasks_passed == 1

    def test_golden_task_fail(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker, golden_task: GoldenTask
    ):
        """Test failing a golden task."""
        # Create golden task
        task = Task(
            prompt=golden_task.prompt,
            task_type=golden_task.task_type,
            status="pending",
            is_golden=True,
            golden_answer=golden_task.expected_answer,
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        # Worker A submits wrong answer
        client.get(f"/tasks/next/{worker_a.id}")
        session.refresh(task)

        client.post(
            "/tasks/submit",
            json={
                "task_id": task.id,
                "worker_id": worker_a.id,
                "result": "wrong_answer"
            }
        )

        # Worker B validates
        client.get(f"/tasks/next/{worker_b.id}")
        session.refresh(task)

        session.refresh(worker_a)
        initial_rep = worker_a.reputation

        response = client.post(
            "/tasks/validate",
            json={
                "task_id": task.id,
                "worker_id": worker_b.id,
                "result": golden_task.expected_answer
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["validation"] == "rejected"
        assert data["reason"] == "golden_failed"

        # Check severe penalty
        session.refresh(worker_a)
        assert worker_a.golden_tasks_failed == 1
        assert worker_a.reputation < initial_rep


class TestTaskRewards:
    """Tests for task reward calculation."""

    def test_reward_by_task_type(
        self, client: TestClient, session: Session,
        worker_a: Worker, worker_b: Worker
    ):
        """Test that different task types give different rewards."""
        task_rewards = []

        for task_type in ["text", "reverse", "math", "llm"]:
            # Create task
            response = client.post(
                "/tasks/create",
                json={"prompt": f"test:{task_type}", "task_type": task_type}
            )
            task_id = response.json()["task_id"]

            # Complete the pipeline
            session.refresh(worker_a)
            initial_balance = worker_a.balance

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
            reward = worker_a.balance - initial_balance
            task_rewards.append((task_type, reward))

        # Verify LLM tasks have higher rewards
        text_reward = next(r for t, r in task_rewards if t == "text")
        llm_reward = next(r for t, r in task_rewards if t == "llm")
        assert llm_reward > text_reward


class TestTaskListing:
    """Tests for task listing and stats."""

    def test_list_tasks(
        self, client: TestClient, pending_task: Task, assigned_task: Task
    ):
        """Test listing tasks."""
        response = client.get("/tasks/")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 2

    def test_list_tasks_filter_by_status(
        self, client: TestClient, pending_task: Task, assigned_task: Task
    ):
        """Test filtering tasks by status."""
        response = client.get("/tasks/?status=pending")

        assert response.status_code == 200
        data = response.json()
        for task in data["tasks"]:
            assert task["status"] == "pending"

    def test_get_task_stats(
        self, client: TestClient, pending_task: Task, assigned_task: Task
    ):
        """Test getting task statistics."""
        response = client.get("/tasks/stats")

        assert response.status_code == 200
        data = response.json()
        assert "pending" in data["stats"]
        assert "assigned" in data["stats"]
        assert "done" in data["stats"]

    def test_get_task_by_id(self, client: TestClient, pending_task: Task):
        """Test getting task details."""
        response = client.get(f"/tasks/{pending_task.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pending_task.id
        assert data["prompt"] == pending_task.prompt


class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_complete_task_pipeline(
        self, client: TestClient, session: Session
    ):
        """Test complete task lifecycle: create -> assign -> submit -> validate."""
        # 1. Register workers
        w1 = client.post(
            "/workers/register",
            json={"name": "Pipeline-A", "power": 5}
        ).json()["worker_id"]

        w2 = client.post(
            "/workers/register",
            json={"name": "Pipeline-B", "power": 5}
        ).json()["worker_id"]

        # 2. Create task
        task_id = client.post(
            "/tasks/create",
            json={"prompt": "reverse:pipeline", "task_type": "reverse"}
        ).json()["task_id"]

        # 3. Worker A gets task
        response = client.get(f"/tasks/next/{w1}")
        assert response.json()["task_id"] == task_id
        assert response.json()["mode"] == "work"

        # 4. Worker A submits
        response = client.post(
            "/tasks/submit",
            json={"task_id": task_id, "worker_id": w1, "result": "enilep"}
        )
        assert response.json()["stage"] == "awaiting_validation"

        # 5. Worker B gets validation task
        response = client.get(f"/tasks/next/{w2}")
        assert response.json()["task_id"] == task_id
        assert response.json()["mode"] == "validate"

        # 6. Worker B validates
        response = client.post(
            "/tasks/validate",
            json={"task_id": task_id, "worker_id": w2, "result": "enilep"}
        )
        assert response.json()["validation"] == "done"

        # 7. Verify final state
        task_response = client.get(f"/tasks/{task_id}")
        assert task_response.json()["status"] == "done"
