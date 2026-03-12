"""
Task management endpoints - Core validation logic with two-tier worker system.
"""

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlmodel import Session, select, func
from sqlalchemy import and_

from ..db import get_session
from ..models import (
    Task, Worker, Transaction, GoldenTask,
    ReputationHistory, AuditLog
)
from ..schemas import TaskCreate, TaskResult
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["Tasks"])


# =============================================================================
# HELPERS
# =============================================================================

def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is timezone-aware (assume UTC if naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def create_transaction(
    session: Session,
    worker: Worker,
    amount: Decimal,
    tx_type: str,
    description: str,
    task_id: int = None,
) -> Transaction:
    """Create transaction and update balance."""
    balance_before = worker.balance
    worker.balance = worker.balance + amount
    if amount > 0:
        worker.total_earned = worker.total_earned + amount

    tx = Transaction(
        worker_id=worker.id,
        type=tx_type,
        amount=amount,
        balance_before=balance_before,
        balance_after=worker.balance,
        description=description,
        task_id=task_id,
    )
    session.add(tx)
    return tx


def update_reputation(
    session: Session,
    worker: Worker,
    change: float,
    reason: str,
    task_id: int = None,
) -> None:
    """Update reputation with history tracking."""
    old_rep = worker.reputation
    new_rep = max(
        Decimal("0.0"),
        min(Decimal("10.0"), old_rep + Decimal(str(change)))
    )
    worker.reputation = new_rep

    # Update level
    rep = float(new_rep)
    if rep >= 5.0:
        worker.reputation_level = "diamond"
    elif rep >= 3.0:
        worker.reputation_level = "platinum"
    elif rep >= 2.0:
        worker.reputation_level = "gold"
    elif rep >= 1.5:
        worker.reputation_level = "silver"
    else:
        worker.reputation_level = "bronze"

    # Log history
    history = ReputationHistory(
        worker_id=worker.id,
        old_reputation=old_rep,
        new_reputation=new_rep,
        change_amount=Decimal(str(change)),
        reason=reason,
        task_id=task_id,
    )
    session.add(history)


def get_task_reward(task_type: str) -> Decimal:
    """Get reward for task type."""
    rewards = {
        "text": Decimal("0.05"),
        "reverse": Decimal("0.10"),
        "math": Decimal("0.15"),
        "llm": Decimal("0.50"),
        "heavy": Decimal("1.00"),
        "sentiment": Decimal("0.05"),
    }
    return rewards.get(task_type, Decimal("0.05"))


# =============================================================================
# CREATE TASK
# =============================================================================

@router.post("/create")
def create_task(
    data: TaskCreate,
    session: Session = Depends(get_session),
):
    """Create new task with optional golden task injection."""

    prompt = data.prompt
    task_type = data.task_type or "text"
    is_golden = False
    golden_answer = None

    # Golden task injection (10% chance)
    if random.random() < 0.1:
        golden = session.exec(
            select(GoldenTask)
            .where(and_(
                GoldenTask.task_type == task_type,
                GoldenTask.is_active == True
            ))
            .order_by(func.random())
            .limit(1)
        ).first()

        if golden:
            is_golden = True
            prompt = golden.prompt
            golden_answer = golden.expected_answer
            golden.times_used += 1
            session.add(golden)

    task = Task(
        prompt=prompt,
        task_type=task_type,
        status="pending",
        priority=getattr(data, 'priority', 0),
        is_golden=is_golden,
        golden_answer=golden_answer,
    )

    session.add(task)
    session.commit()
    session.refresh(task)

    return {"task_id": task.id, "status": "created"}


# =============================================================================
# GET NEXT TASK
# =============================================================================

@router.get("/next/{worker_id}")
def get_next_task(
    worker_id: int,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Get next available task for worker."""

    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")
    if worker.is_banned:
        raise HTTPException(403, "Worker is banned")

    # Update worker
    worker.last_seen = datetime.now(timezone.utc)
    worker.status = "online"
    session.add(worker)

    lease_expires = datetime.now(timezone.utc) + timedelta(seconds=300)

    # Priority 1: Validation tasks
    validation_task = session.exec(
        select(Task).where(and_(
            Task.status == "submitted_A",
            Task.worker_id != worker_id,
            Task.validator_worker_id == None,
        ))
        .order_by(Task.priority.desc(), Task.id.asc())
    ).first()

    if validation_task:
        validation_task.status = "validating"
        validation_task.validator_worker_id = worker_id
        validation_task.lease_expires_at = lease_expires
        validation_task.updated_at = datetime.now(timezone.utc)
        worker.status = "working"

        session.add(validation_task)
        session.add(worker)
        session.commit()

        return {
            "task_id": validation_task.id,
            "prompt": validation_task.prompt,
            "task_type": validation_task.task_type,
            "mode": "validate",
        }

    # Priority 2: New tasks
    task = session.exec(
        select(Task)
        .where(Task.status == "pending")
        .order_by(Task.priority.desc(), Task.id.asc())
    ).first()

    if not task:
        return {"task": None}

    task.status = "assigned"
    task.worker_id = worker_id
    task.lease_expires_at = lease_expires
    task.updated_at = datetime.now(timezone.utc)
    worker.status = "working"
    worker.last_task_at = datetime.now(timezone.utc)

    session.add(task)
    session.add(worker)
    session.commit()

    return {
        "task_id": task.id,
        "prompt": task.prompt,
        "task_type": task.task_type,
        "mode": "work",
    }


# =============================================================================
# SUBMIT RESULT (Worker A)
# =============================================================================

@router.post("/submit")
def submit_result(
    data: TaskResult,
    session: Session = Depends(get_session),
):
    """Worker A submits task result."""

    task = session.get(Task, data.task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "assigned":
        raise HTTPException(400, f"Invalid state: {task.status}")
    if task.worker_id != data.worker_id:
        raise HTTPException(403, "Not your task")

    worker = session.get(Worker, data.worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    # Check lease
    if task.lease_expires_at and datetime.now(timezone.utc) > ensure_aware(task.lease_expires_at):
        task.status = "pending"
        task.worker_id = None
        session.add(task)
        session.commit()
        raise HTTPException(408, "Lease expired")

    # Store result
    task.result = data.result
    task.result_hash = hashlib.sha256(data.result.encode()).hexdigest()
    task.status = "submitted_A"
    task.submitted_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    task.lease_expires_at = None

    worker.status = "idle"
    worker.last_seen = datetime.now(timezone.utc)

    session.add(task)
    session.add(worker)
    session.commit()

    return {"status": "ok", "stage": "awaiting_validation"}


# =============================================================================
# VALIDATE (Worker B) - CORE LOGIC
# =============================================================================

@router.post("/validate")
def validate_task(
    data: TaskResult,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Worker B validates Worker A's result.

    Match: Both rewarded, reputation up
    Mismatch: Worker A penalized, Worker B bonus
    Golden fail: Severe penalty for Worker A
    """

    task = session.get(Task, data.task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "validating":
        raise HTTPException(400, f"Invalid state: {task.status}")
    if task.validator_worker_id != data.worker_id:
        raise HTTPException(403, "Not assigned validator")

    worker_A = session.get(Worker, task.worker_id)
    worker_B = session.get(Worker, task.validator_worker_id)

    if not worker_A or not worker_B:
        raise HTTPException(404, "Worker not found")

    # Store validator result
    task.validator_result = data.result
    task.validator_result_hash = hashlib.sha256(data.result.encode()).hexdigest()
    task.validated_at = datetime.now(timezone.utc)

    result_A = task.result
    result_B = data.result
    base_reward = get_task_reward(task.task_type)

    # ═══════════════════════════════════════════════════════════════
    # GOLDEN TASK CHECK
    # ═══════════════════════════════════════════════════════════════
    if task.is_golden and task.golden_answer:
        if result_A != task.golden_answer:
            # Worker A failed honeypot
            worker_A.golden_tasks_failed += 1
            update_reputation(session, worker_A, -0.2, f"Failed golden task #{task.id}", task.id)

            task.status = "rejected"
            worker_A.tasks_failed += 1
            worker_B.validations_completed += 1
            worker_A.status = "idle"
            worker_B.status = "idle"

            session.add_all([task, worker_A, worker_B])
            session.commit()

            return {"status": "ok", "validation": "rejected", "reason": "golden_failed"}
        else:
            worker_A.golden_tasks_passed += 1

    # ═══════════════════════════════════════════════════════════════
    # MATCH - SUCCESS
    # ═══════════════════════════════════════════════════════════════
    if result_A == result_B:
        task.status = "done"
        task.confidence = Decimal("1.0")

        reward_A = base_reward
        reward_B = base_reward * Decimal("0.4")

        task.reward_worker_a = reward_A
        task.reward_worker_b = reward_B

        create_transaction(session, worker_A, reward_A, "reward",
                          f"Task #{task.id} completed", task.id)
        create_transaction(session, worker_B, reward_B, "reward",
                          f"Validated task #{task.id}", task.id)

        update_reputation(session, worker_A, 0.01, f"Task #{task.id} success", task.id)
        update_reputation(session, worker_B, 0.005, f"Validated #{task.id}", task.id)

        worker_A.tasks_completed += 1
        worker_B.validations_completed += 1

        validation_result = "done"

    # ═══════════════════════════════════════════════════════════════
    # MISMATCH - FAILURE
    # ═══════════════════════════════════════════════════════════════
    else:
        task.status = "rejected"
        task.confidence = Decimal("0.0")

        update_reputation(session, worker_A, -0.1, f"Task #{task.id} mismatch", task.id)
        update_reputation(session, worker_B, 0.01, f"Caught mismatch #{task.id}", task.id)

        # Bonus for catching error
        bonus = Decimal("0.01")
        create_transaction(session, worker_B, bonus, "bonus",
                          f"Caught mismatch #{task.id}", task.id)

        worker_A.tasks_failed += 1
        worker_B.validations_completed += 1

        validation_result = "rejected"

    # Reset workers
    worker_A.status = "idle"
    worker_B.status = "idle"
    worker_A.last_seen = datetime.now(timezone.utc)
    worker_B.last_seen = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)

    session.add_all([task, worker_A, worker_B])
    session.commit()

    return {"status": "ok", "validation": validation_result}


# =============================================================================
# ADDITIONAL ENDPOINTS
# =============================================================================

@router.get("/")
def list_tasks(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session)
):
    """List all tasks with optional filtering."""
    query = select(Task).order_by(Task.created_at.desc())

    if status:
        query = query.where(Task.status == status)

    query = query.offset(offset).limit(limit)
    tasks = session.exec(query).all()

    return {
        "tasks": [
            {
                "id": t.id,
                "prompt": t.prompt,
                "task_type": t.task_type,
                "status": t.status,
                "worker_id": t.worker_id,
                "validator_worker_id": t.validator_worker_id,
                "is_golden": t.is_golden,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "count": len(tasks),
        "offset": offset,
        "limit": limit,
    }


@router.get("/stats")
def get_task_stats(session: Session = Depends(get_session)):
    """Get task statistics."""
    stats = {}
    for status in ["pending", "assigned", "submitted_A", "validating", "done", "rejected"]:
        count = session.exec(
            select(func.count(Task.id)).where(Task.status == status)
        ).one()
        stats[status] = count
    return {"stats": stats}


@router.get("/{task_id}")
def get_task(task_id: int, session: Session = Depends(get_session)):
    """Get task details."""
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    return {
        "id": task.id,
        "prompt": task.prompt,
        "task_type": task.task_type,
        "status": task.status,
        "worker_id": task.worker_id,
        "validator_worker_id": task.validator_worker_id,
        "confidence": float(task.confidence) if task.confidence else 0,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@router.post("/expire-leases")
def expire_stale_leases(session: Session = Depends(get_session)):
    """Reset expired task leases."""
    now = datetime.now(timezone.utc)
    count = 0

    # Expired assigned
    tasks = session.exec(
        select(Task).where(and_(
            Task.status == "assigned",
            Task.lease_expires_at < now,
        ))
    ).all()

    for task in tasks:
        task.status = "pending"
        task.worker_id = None
        task.lease_expires_at = None
        session.add(task)
        count += 1

    # Expired validating
    tasks = session.exec(
        select(Task).where(and_(
            Task.status == "validating",
            Task.lease_expires_at < now,
        ))
    ).all()

    for task in tasks:
        task.status = "submitted_A"
        task.validator_worker_id = None
        task.lease_expires_at = None
        session.add(task)
        count += 1

    session.commit()
    return {"expired_count": count}
