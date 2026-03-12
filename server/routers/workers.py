"""
Worker management endpoints for the Distributed AI Network.
Handles registration, status updates, heartbeats, and worker queries.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select, func, col
from sqlalchemy import and_

from ..db import get_session
from ..models import Worker, WorkerStatus, AuditLog, AuditAction, ReputationHistory
from ..schemas import (
    WorkerRegister,
    WorkerResponse,
    WorkerListResponse,
    WorkerStatsResponse,
    SuccessResponse,
    ErrorResponse,
)
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["Workers"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def log_audit(
    session: Session,
    action: str,
    actor_type: str,
    actor_id: Optional[int],
    target_type: Optional[str],
    target_id: Optional[int],
    details: dict,
    request: Optional[Request] = None,
) -> None:
    """Log an audit event."""
    audit = AuditLog(
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    session.add(audit)


# =============================================================================
# REGISTRATION
# =============================================================================

@router.post("/register", response_model=dict)
def register_worker(
    data: WorkerRegister,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Register a new worker in the network.

    Workers start with:
    - Balance: 0
    - Reputation: 1.0
    - Reputation Level: bronze
    - Status: idle
    """
    logger.info(f"Registering new worker: {data.name}")

    # Create worker
    worker = Worker(
        name=data.name,
        power=data.power,
        capabilities=data.capabilities,
        fingerprint=data.fingerprint,
        balance=Decimal("0.0"),
        reputation=Decimal("1.0"),
        reputation_level="bronze",
        status=WorkerStatus.IDLE.value,
        is_banned=False,
    )

    session.add(worker)
    session.flush()  # Get the ID

    # Log audit event
    log_audit(
        session=session,
        action=AuditAction.WORKER_REGISTER.value,
        actor_type="worker",
        actor_id=worker.id,
        target_type="worker",
        target_id=worker.id,
        details={
            "name": worker.name,
            "power": worker.power,
            "capabilities": worker.capabilities,
        },
        request=request,
    )

    session.commit()

    logger.info(f"Worker registered: id={worker.id}, name={worker.name}")

    return {
        "worker_id": worker.id,
        "uuid": worker.uuid,
        "reputation": float(worker.reputation),
        "status": "registered",
    }


# =============================================================================
# WORKER INFO
# =============================================================================

@router.get("/{worker_id}", response_model=WorkerResponse)
def get_worker(
    worker_id: int,
    session: Session = Depends(get_session),
):
    """Get detailed information about a worker."""
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Calculate success rate
    total = worker.tasks_completed + worker.tasks_failed
    success_rate = (worker.tasks_completed / total * 100) if total > 0 else 0.0

    return WorkerResponse(
        id=worker.id,
        uuid=worker.uuid,
        name=worker.name,
        power=worker.power,
        capabilities=worker.capabilities,
        balance=worker.balance,
        pending_balance=worker.pending_balance,
        reputation=worker.reputation,
        reputation_level=worker.reputation_level,
        tasks_completed=worker.tasks_completed,
        tasks_failed=worker.tasks_failed,
        validations_completed=worker.validations_completed,
        success_rate=success_rate,
        status=worker.status,
        is_banned=worker.is_banned,
        last_seen=worker.last_seen,
        created_at=worker.created_at,
    )


@router.get("/uuid/{worker_uuid}", response_model=WorkerResponse)
def get_worker_by_uuid(
    worker_uuid: str,
    session: Session = Depends(get_session),
):
    """Get worker by UUID."""
    statement = select(Worker).where(Worker.uuid == worker_uuid)
    worker = session.exec(statement).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    total = worker.tasks_completed + worker.tasks_failed
    success_rate = (worker.tasks_completed / total * 100) if total > 0 else 0.0

    return WorkerResponse(
        id=worker.id,
        uuid=worker.uuid,
        name=worker.name,
        power=worker.power,
        capabilities=worker.capabilities,
        balance=worker.balance,
        pending_balance=worker.pending_balance,
        reputation=worker.reputation,
        reputation_level=worker.reputation_level,
        tasks_completed=worker.tasks_completed,
        tasks_failed=worker.tasks_failed,
        validations_completed=worker.validations_completed,
        success_rate=success_rate,
        status=worker.status,
        is_banned=worker.is_banned,
        last_seen=worker.last_seen,
        created_at=worker.created_at,
    )


# =============================================================================
# WORKER LIST
# =============================================================================

@router.get("/", response_model=WorkerListResponse)
def list_workers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    include_banned: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    """
    List workers with pagination and filtering.

    - **page**: Page number (1-indexed)
    - **page_size**: Items per page (max 100)
    - **status**: Filter by status (idle, online, working, offline)
    - **include_banned**: Include banned workers
    """
    # Build query
    query = select(Worker)

    if not include_banned:
        query = query.where(Worker.is_banned == False)

    if status:
        query = query.where(Worker.status == status)

    # Get total count
    count_query = select(func.count(Worker.id))
    if not include_banned:
        count_query = count_query.where(Worker.is_banned == False)
    if status:
        count_query = count_query.where(Worker.status == status)

    total = session.exec(count_query).one()

    # Get paginated results
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Worker.id.desc())
    workers = session.exec(query).all()

    # Build response
    worker_responses = []
    for w in workers:
        total_tasks = w.tasks_completed + w.tasks_failed
        success_rate = (w.tasks_completed / total_tasks * 100) if total_tasks > 0 else 0.0

        worker_responses.append(WorkerResponse(
            id=w.id,
            uuid=w.uuid,
            name=w.name,
            power=w.power,
            capabilities=w.capabilities,
            balance=w.balance,
            pending_balance=w.pending_balance,
            reputation=w.reputation,
            reputation_level=w.reputation_level,
            tasks_completed=w.tasks_completed,
            tasks_failed=w.tasks_failed,
            validations_completed=w.validations_completed,
            success_rate=success_rate,
            status=w.status,
            is_banned=w.is_banned,
            last_seen=w.last_seen,
            created_at=w.created_at,
        ))

    return WorkerListResponse(
        workers=worker_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# HEARTBEAT
# =============================================================================

@router.post("/heartbeat", response_model=SuccessResponse)
def heartbeat(
    worker_id: int = Query(..., description="Worker ID"),
    session: Session = Depends(get_session),
):
    """
    Worker heartbeat to maintain online status.

    Workers should send heartbeats every 30 seconds.
    Workers not seen for 2 minutes are marked offline.
    """
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.is_banned:
        raise HTTPException(status_code=403, detail="Worker is banned")

    # Update last seen
    worker.last_seen = datetime.now(timezone.utc)

    # Update status to online if idle
    if worker.status == WorkerStatus.IDLE.value:
        worker.status = WorkerStatus.ONLINE.value

    session.add(worker)
    session.commit()

    return SuccessResponse(status="ok", message="Heartbeat received")


# =============================================================================
# STATUS UPDATE
# =============================================================================

@router.post("/status/{worker_id}", response_model=SuccessResponse)
def update_worker_status(
    worker_id: int,
    status: str = Query(..., description="New status"),
    session: Session = Depends(get_session),
):
    """Update worker status."""
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.is_banned:
        raise HTTPException(status_code=403, detail="Worker is banned")

    # Validate status
    valid_statuses = [s.value for s in WorkerStatus if s != WorkerStatus.BANNED]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    worker.status = status
    worker.last_seen = datetime.now(timezone.utc)
    worker.updated_at = datetime.now(timezone.utc)

    session.add(worker)
    session.commit()

    return SuccessResponse(status="ok", message=f"Status updated to {status}")


# =============================================================================
# STATISTICS
# =============================================================================

@router.get("/stats/summary", response_model=WorkerStatsResponse)
def get_worker_stats(
    session: Session = Depends(get_session),
):
    """Get aggregate worker statistics."""
    # Total workers
    total_workers = session.exec(select(func.count(Worker.id))).one()

    # Active workers (seen in last 5 minutes)
    active_threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    active_workers = session.exec(
        select(func.count(Worker.id))
        .where(and_(
            Worker.last_seen >= active_threshold,
            Worker.is_banned == False
        ))
    ).one()

    # Working workers
    working_workers = session.exec(
        select(func.count(Worker.id))
        .where(and_(
            Worker.status == WorkerStatus.WORKING.value,
            Worker.is_banned == False
        ))
    ).one()

    # Banned workers
    banned_workers = session.exec(
        select(func.count(Worker.id))
        .where(Worker.is_banned == True)
    ).one()

    # Total balance
    total_balance = session.exec(
        select(func.sum(Worker.balance))
        .where(Worker.is_banned == False)
    ).one() or Decimal("0.0")

    # Average reputation
    avg_reputation = session.exec(
        select(func.avg(Worker.reputation))
        .where(Worker.is_banned == False)
    ).one() or 0.0

    return WorkerStatsResponse(
        total_workers=total_workers,
        active_workers=active_workers,
        working_workers=working_workers,
        banned_workers=banned_workers,
        total_balance=total_balance,
        avg_reputation=float(avg_reputation),
    )


# =============================================================================
# LEADERBOARD
# =============================================================================

@router.get("/leaderboard/reputation")
def get_reputation_leaderboard(
    limit: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Get top workers by reputation."""
    statement = (
        select(Worker)
        .where(Worker.is_banned == False)
        .order_by(Worker.reputation.desc())
        .limit(limit)
    )
    workers = session.exec(statement).all()

    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "worker_id": w.id,
                "name": w.name,
                "reputation": float(w.reputation),
                "reputation_level": w.reputation_level,
                "tasks_completed": w.tasks_completed,
            }
            for i, w in enumerate(workers)
        ]
    }


@router.get("/leaderboard/earnings")
def get_earnings_leaderboard(
    limit: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Get top workers by total earnings."""
    statement = (
        select(Worker)
        .where(Worker.is_banned == False)
        .order_by(Worker.total_earned.desc())
        .limit(limit)
    )
    workers = session.exec(statement).all()

    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "worker_id": w.id,
                "name": w.name,
                "total_earned": float(w.total_earned),
                "balance": float(w.balance),
                "tasks_completed": w.tasks_completed,
            }
            for i, w in enumerate(workers)
        ]
    }


# =============================================================================
# WORKER TRANSACTIONS HISTORY
# =============================================================================

@router.get("/{worker_id}/transactions")
def get_worker_transactions(
    worker_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Get transaction history for a worker."""
    from ..models import Transaction

    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Count total
    count_query = select(func.count(Transaction.id)).where(Transaction.worker_id == worker_id)
    total = session.exec(count_query).one()

    # Get transactions
    offset = (page - 1) * page_size
    statement = (
        select(Transaction)
        .where(Transaction.worker_id == worker_id)
        .order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    transactions = session.exec(statement).all()

    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.type,
                "amount": float(t.amount),
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "description": t.description,
                "task_id": t.task_id,
                "created_at": t.created_at.isoformat(),
            }
            for t in transactions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# =============================================================================
# REPUTATION HISTORY
# =============================================================================

@router.get("/{worker_id}/reputation/history")
def get_reputation_history(
    worker_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """Get reputation change history for a worker."""
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    statement = (
        select(ReputationHistory)
        .where(ReputationHistory.worker_id == worker_id)
        .order_by(ReputationHistory.created_at.desc())
        .limit(limit)
    )
    history = session.exec(statement).all()

    return {
        "current_reputation": float(worker.reputation),
        "reputation_level": worker.reputation_level,
        "history": [
            {
                "id": h.id,
                "old_reputation": float(h.old_reputation),
                "new_reputation": float(h.new_reputation),
                "change_amount": float(h.change_amount),
                "reason": h.reason,
                "task_id": h.task_id,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ],
    }
