"""
Admin panel endpoints for the Distributed AI Network.
Provides dashboard, worker management, and system oversight.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func
from sqlalchemy import and_, or_

from ..db import get_session
from ..models import (
    Worker, Task, Transaction, WithdrawalRequest,
    AuditLog, AuditAction, GoldenTask, ReputationHistory
)
from ..schemas import BanWorkerRequest, UnbanWorkerRequest, SuccessResponse
from ..config import settings
from ..collusion import (
    analyze_worker, run_full_scan, auto_ban_colluders,
    find_collusion_rings, COLLUSION_SCORE_THRESHOLD
)
from ..reputation_decay import (
    run_decay_job, get_decay_preview,
    GRACE_PERIOD_DAYS, DECAY_RATES, MIN_REPUTATION
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# HELPERS
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
    """Log audit event."""
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
# DASHBOARD
# =============================================================================

@router.get("/dashboard")
def get_dashboard(session: Session = Depends(get_session)):
    """
    Get comprehensive dashboard statistics.

    Returns worker, task, and financial metrics.
    """
    now = datetime.now(timezone.utc)
    active_threshold = now - timedelta(minutes=5)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    # Worker stats
    total_workers = session.exec(select(func.count(Worker.id))).one()
    active_workers = session.exec(
        select(func.count(Worker.id))
        .where(and_(
            Worker.last_seen >= active_threshold,
            Worker.is_banned == False
        ))
    ).one()
    working_workers = session.exec(
        select(func.count(Worker.id))
        .where(Worker.status == "working")
    ).one()
    banned_workers = session.exec(
        select(func.count(Worker.id))
        .where(Worker.is_banned == True)
    ).one()

    # Task stats
    task_stats = {}
    for status in ["pending", "assigned", "submitted_A", "validating", "done", "rejected"]:
        count = session.exec(
            select(func.count(Task.id))
            .where(Task.status == status)
        ).one()
        task_stats[status] = count

    tasks_today = session.exec(
        select(func.count(Task.id))
        .where(Task.created_at >= day_ago)
    ).one()

    tasks_completed_today = session.exec(
        select(func.count(Task.id))
        .where(and_(
            Task.status == "done",
            Task.validated_at >= day_ago
        ))
    ).one()

    # Financial stats
    total_balance = session.exec(
        select(func.sum(Worker.balance))
    ).one() or Decimal("0.0")

    total_earned = session.exec(
        select(func.sum(Worker.total_earned))
    ).one() or Decimal("0.0")

    pending_withdrawals = session.exec(
        select(func.sum(WithdrawalRequest.amount))
        .where(WithdrawalRequest.status == "pending")
    ).one() or Decimal("0.0")

    paid_today = session.exec(
        select(func.sum(WithdrawalRequest.amount))
        .where(and_(
            WithdrawalRequest.status == "paid",
            WithdrawalRequest.processed_at >= day_ago
        ))
    ).one() or Decimal("0.0")

    # Reputation stats
    avg_reputation = session.exec(
        select(func.avg(Worker.reputation))
        .where(Worker.is_banned == False)
    ).one() or 0.0

    return {
        "workers": {
            "total": total_workers,
            "active": active_workers,
            "working": working_workers,
            "banned": banned_workers,
            "avg_reputation": round(float(avg_reputation), 3),
        },
        "tasks": {
            **task_stats,
            "today": tasks_today,
            "completed_today": tasks_completed_today,
        },
        "financial": {
            "total_balance": float(total_balance),
            "total_earned": float(total_earned),
            "pending_withdrawals": float(pending_withdrawals),
            "paid_today": float(paid_today),
        },
        "generated_at": now.isoformat(),
    }


# =============================================================================
# WORKER MANAGEMENT
# =============================================================================

@router.post("/ban")
def ban_worker(
    data: BanWorkerRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Ban a worker from the network.

    - Cancels pending withdrawals (refunds balance)
    - Cancels assigned tasks
    - Logs audit event
    """
    worker = session.get(Worker, data.worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    if worker.is_banned:
        raise HTTPException(400, "Worker already banned")

    # Ban worker
    worker.is_banned = True
    worker.status = "banned"
    worker.updated_at = datetime.now(timezone.utc)

    # Cancel pending withdrawals
    pending_withdrawals = session.exec(
        select(WithdrawalRequest)
        .where(and_(
            WithdrawalRequest.worker_id == data.worker_id,
            WithdrawalRequest.status == "pending"
        ))
    ).all()

    for withdrawal in pending_withdrawals:
        worker.balance += withdrawal.amount
        withdrawal.status = "cancelled"
        withdrawal.rejection_reason = f"Worker banned: {data.reason}"
        withdrawal.processed_at = datetime.now(timezone.utc)
        session.add(withdrawal)

    # Release assigned tasks
    assigned_tasks = session.exec(
        select(Task)
        .where(and_(
            Task.worker_id == data.worker_id,
            Task.status.in_(["assigned", "submitted_A"])
        ))
    ).all()

    for task in assigned_tasks:
        task.status = "pending"
        task.worker_id = None
        task.result = None
        task.result_hash = None
        session.add(task)

    # Audit log
    log_audit(
        session,
        action=AuditAction.WORKER_BAN.value,
        actor_type="admin",
        actor_id=None,
        target_type="worker",
        target_id=data.worker_id,
        details={
            "reason": data.reason,
            "cancelled_withdrawals": len(pending_withdrawals),
            "released_tasks": len(assigned_tasks),
        },
        request=request,
    )

    session.add(worker)
    session.commit()

    logger.warning(f"Worker {data.worker_id} banned: {data.reason}")

    return {
        "status": "banned",
        "worker_id": data.worker_id,
        "cancelled_withdrawals": len(pending_withdrawals),
        "released_tasks": len(assigned_tasks),
    }


@router.post("/unban")
def unban_worker(
    data: UnbanWorkerRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    """Unban a worker."""
    worker = session.get(Worker, data.worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    if not worker.is_banned:
        raise HTTPException(400, "Worker not banned")

    worker.is_banned = False
    worker.status = "idle"
    worker.updated_at = datetime.now(timezone.utc)

    log_audit(
        session,
        action=AuditAction.WORKER_UNBAN.value,
        actor_type="admin",
        actor_id=None,
        target_type="worker",
        target_id=data.worker_id,
        details={},
        request=request,
    )

    session.add(worker)
    session.commit()

    logger.info(f"Worker {data.worker_id} unbanned")

    return {"status": "unbanned", "worker_id": data.worker_id}


@router.post("/reset-reputation/{worker_id}")
def reset_reputation(
    worker_id: int,
    new_reputation: float = 1.0,
    reason: str = "Admin reset",
    request: Request = None,
    session: Session = Depends(get_session),
):
    """Reset worker reputation to specified value."""
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    if new_reputation < 0 or new_reputation > 10:
        raise HTTPException(400, "Reputation must be 0-10")

    old_rep = worker.reputation
    worker.reputation = Decimal(str(new_reputation))

    # Update level
    if new_reputation >= 5.0:
        worker.reputation_level = "diamond"
    elif new_reputation >= 3.0:
        worker.reputation_level = "platinum"
    elif new_reputation >= 2.0:
        worker.reputation_level = "gold"
    elif new_reputation >= 1.5:
        worker.reputation_level = "silver"
    else:
        worker.reputation_level = "bronze"

    # Log history
    history = ReputationHistory(
        worker_id=worker_id,
        old_reputation=old_rep,
        new_reputation=worker.reputation,
        change_amount=worker.reputation - old_rep,
        reason=f"Admin reset: {reason}",
    )
    session.add(history)

    log_audit(
        session,
        action="reputation_reset",
        actor_type="admin",
        actor_id=None,
        target_type="worker",
        target_id=worker_id,
        details={
            "old_reputation": float(old_rep),
            "new_reputation": new_reputation,
            "reason": reason,
        },
        request=request,
    )

    session.add(worker)
    session.commit()

    return {
        "status": "ok",
        "worker_id": worker_id,
        "old_reputation": float(old_rep),
        "new_reputation": new_reputation,
    }


# =============================================================================
# GOLDEN TASKS
# =============================================================================

@router.post("/golden-tasks")
def create_golden_task(
    prompt: str,
    expected_answer: str,
    task_type: str = "text",
    session: Session = Depends(get_session),
):
    """Create a new golden (honeypot) task."""
    golden = GoldenTask(
        prompt=prompt,
        expected_answer=expected_answer,
        task_type=task_type,
        is_active=True,
    )
    session.add(golden)
    session.commit()
    session.refresh(golden)

    logger.info(f"Golden task #{golden.id} created")

    return {"status": "created", "golden_task_id": golden.id}


@router.get("/golden-tasks")
def list_golden_tasks(
    task_type: Optional[str] = None,
    active_only: bool = True,
    session: Session = Depends(get_session),
):
    """List golden tasks."""
    query = select(GoldenTask)

    if task_type:
        query = query.where(GoldenTask.task_type == task_type)

    if active_only:
        query = query.where(GoldenTask.is_active == True)

    golden_tasks = session.exec(query.order_by(GoldenTask.id.desc())).all()

    return {
        "golden_tasks": [
            {
                "id": g.id,
                "prompt": g.prompt,
                "expected_answer": g.expected_answer,
                "task_type": g.task_type,
                "is_active": g.is_active,
                "times_used": g.times_used,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in golden_tasks
        ]
    }


@router.post("/golden-tasks/{golden_id}/toggle")
def toggle_golden_task(
    golden_id: int,
    session: Session = Depends(get_session),
):
    """Toggle golden task active status."""
    golden = session.get(GoldenTask, golden_id)
    if not golden:
        raise HTTPException(404, "Golden task not found")

    golden.is_active = not golden.is_active
    session.add(golden)
    session.commit()

    return {"status": "ok", "is_active": golden.is_active}


# =============================================================================
# AUDIT LOG
# =============================================================================

@router.get("/audit-log")
def get_audit_log(
    action: Optional[str] = None,
    actor_type: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """Get audit log with filtering."""
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    if actor_type:
        query = query.where(AuditLog.actor_type == actor_type)
        count_query = count_query.where(AuditLog.actor_type == actor_type)

    if target_type:
        query = query.where(AuditLog.target_type == target_type)
        count_query = count_query.where(AuditLog.target_type == target_type)

    if target_id:
        query = query.where(AuditLog.target_id == target_id)
        count_query = count_query.where(AuditLog.target_id == target_id)

    total = session.exec(count_query).one()

    offset = (page - 1) * page_size
    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    logs = session.exec(query).all()

    return {
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "actor_type": log.actor_type,
                "actor_id": log.actor_id,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# =============================================================================
# SYSTEM
# =============================================================================

@router.post("/cleanup-stale")
def cleanup_stale_workers(
    minutes: int = 30,
    session: Session = Depends(get_session),
):
    """Mark workers not seen for X minutes as offline."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    workers = session.exec(
        select(Worker)
        .where(and_(
            Worker.last_seen < threshold,
            Worker.status != "offline",
            Worker.is_banned == False
        ))
    ).all()

    count = 0
    for worker in workers:
        worker.status = "offline"
        session.add(worker)
        count += 1

    session.commit()

    return {"status": "ok", "marked_offline": count}


@router.get("/system-stats")
def get_system_stats(session: Session = Depends(get_session)):
    """Get detailed system statistics."""
    # Task processing rate
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)

    tasks_last_hour = session.exec(
        select(func.count(Task.id))
        .where(and_(
            Task.status == "done",
            Task.validated_at >= hour_ago
        ))
    ).one()

    tasks_last_day = session.exec(
        select(func.count(Task.id))
        .where(and_(
            Task.status == "done",
            Task.validated_at >= day_ago
        ))
    ).one()

    # Rejection rate
    total_validated = session.exec(
        select(func.count(Task.id))
        .where(Task.status.in_(["done", "rejected"]))
    ).one()

    rejected = session.exec(
        select(func.count(Task.id))
        .where(Task.status == "rejected")
    ).one()

    rejection_rate = (rejected / total_validated * 100) if total_validated > 0 else 0

    # Golden task stats
    golden_passed = session.exec(
        select(func.sum(Worker.golden_tasks_passed))
    ).one() or 0

    golden_failed = session.exec(
        select(func.sum(Worker.golden_tasks_failed))
    ).one() or 0

    golden_pass_rate = (
        golden_passed / (golden_passed + golden_failed) * 100
        if (golden_passed + golden_failed) > 0 else 0
    )

    # Transaction volume
    tx_volume_day = session.exec(
        select(func.sum(Transaction.amount))
        .where(and_(
            Transaction.amount > 0,
            Transaction.created_at >= day_ago
        ))
    ).one() or Decimal("0.0")

    return {
        "processing": {
            "tasks_last_hour": tasks_last_hour,
            "tasks_last_day": tasks_last_day,
            "tasks_per_minute": round(tasks_last_hour / 60, 2),
        },
        "quality": {
            "total_validated": total_validated,
            "rejected": rejected,
            "rejection_rate": round(rejection_rate, 2),
        },
        "golden_tasks": {
            "passed": golden_passed,
            "failed": golden_failed,
            "pass_rate": round(golden_pass_rate, 2),
        },
        "financial": {
            "transaction_volume_24h": float(tx_volume_day),
        },
        "generated_at": now.isoformat(),
    }


@router.get("/problematic-workers")
def get_problematic_workers(
    min_failures: int = 5,
    max_reputation: float = 1.0,
    limit: int = 20,
    session: Session = Depends(get_session),
):
    """Get workers with high failure rates or low reputation."""
    workers = session.exec(
        select(Worker)
        .where(and_(
            Worker.is_banned == False,
            or_(
                Worker.tasks_failed >= min_failures,
                Worker.reputation <= Decimal(str(max_reputation))
            )
        ))
        .order_by(Worker.reputation.asc())
        .limit(limit)
    ).all()

    return {
        "workers": [
            {
                "id": w.id,
                "name": w.name,
                "reputation": float(w.reputation),
                "reputation_level": w.reputation_level,
                "tasks_completed": w.tasks_completed,
                "tasks_failed": w.tasks_failed,
                "golden_passed": w.golden_tasks_passed,
                "golden_failed": w.golden_tasks_failed,
                "failure_rate": round(
                    w.tasks_failed / (w.tasks_completed + w.tasks_failed) * 100
                    if (w.tasks_completed + w.tasks_failed) > 0 else 0,
                    2
                ),
            }
            for w in workers
        ]
    }


# =============================================================================
# COLLUSION DETECTION
# =============================================================================

@router.get("/collusion/analyze/{worker_id}")
def analyze_worker_collusion(
    worker_id: int,
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
):
    """
    Analyze a specific worker for collusion patterns.

    Returns evidence of:
    - Mutual validation patterns
    - Suspicious approval rates
    - Timing anomalies
    """
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    report = analyze_worker(session, worker_id, days)

    return {
        "worker_id": worker_id,
        "worker_name": worker.name,
        "total_score": report.total_score,
        "is_suspicious": report.is_suspicious,
        "recommendation": report.recommendation,
        "threshold": COLLUSION_SCORE_THRESHOLD,
        "evidence": [
            {
                "type": e.evidence_type,
                "score": e.score,
                "description": e.description,
                "worker_ids": list(e.worker_ids),
                "details": e.details,
            }
            for e in report.evidence
        ],
        "analysis_days": days,
    }


@router.get("/collusion/scan")
def scan_all_workers_collusion(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
):
    """
    Run collusion analysis on all active workers.

    Returns only suspicious workers.
    """
    reports = run_full_scan(session, days)

    return {
        "suspicious_workers": [
            {
                "worker_id": wid,
                "score": report.total_score,
                "recommendation": report.recommendation,
                "evidence_count": len(report.evidence),
                "evidence_types": list(set(e.evidence_type for e in report.evidence)),
            }
            for wid, report in reports.items()
        ],
        "total_suspicious": len(reports),
        "analysis_days": days,
        "threshold": COLLUSION_SCORE_THRESHOLD,
    }


@router.get("/collusion/rings")
def find_worker_rings(
    min_ring_size: int = Query(default=3, ge=2, le=10),
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
):
    """
    Find potential collusion rings (groups of workers who validate each other).
    """
    rings = find_collusion_rings(session, min_ring_size, days)

    return {
        "rings": [
            {
                "worker_ids": list(e.worker_ids),
                "ring_size": len(e.worker_ids),
                "score": e.score,
                "description": e.description,
            }
            for e in rings
        ],
        "total_rings": len(rings),
        "min_ring_size": min_ring_size,
        "analysis_days": days,
    }


@router.post("/collusion/auto-ban")
def auto_ban_colluding_workers(
    days: int = Query(default=30, ge=1, le=365),
    dry_run: bool = Query(default=True),
    request: Request = None,
    session: Session = Depends(get_session),
):
    """
    Automatically ban workers with very high collusion scores.

    Set dry_run=false to actually ban workers.
    """
    reports = run_full_scan(session, days)
    banned = auto_ban_colluders(session, reports, dry_run=dry_run)

    if not dry_run and banned:
        log_audit(
            session,
            action="collusion_auto_ban",
            actor_type="system",
            actor_id=None,
            target_type="workers",
            target_id=None,
            details={
                "banned_workers": banned,
                "analysis_days": days,
            },
            request=request,
        )
        session.commit()

    return {
        "dry_run": dry_run,
        "workers_to_ban" if dry_run else "workers_banned": banned,
        "count": len(banned),
        "analysis_days": days,
    }


# =============================================================================
# REPUTATION DECAY
# =============================================================================

@router.get("/reputation-decay/config")
def get_decay_config():
    """Get current reputation decay configuration."""
    return {
        "grace_period_days": GRACE_PERIOD_DAYS,
        "decay_rates": {k: float(v) for k, v in DECAY_RATES.items()},
        "minimum_reputation": float(MIN_REPUTATION),
        "enabled": settings.feature_reputation_decay,
    }


@router.get("/reputation-decay/preview/{worker_id}")
def preview_worker_decay(
    worker_id: int,
    session: Session = Depends(get_session),
):
    """
    Preview what decay would be applied to a specific worker.
    """
    preview = get_decay_preview(session, worker_id)
    if "error" in preview:
        raise HTTPException(404, preview["error"])
    return preview


@router.post("/reputation-decay/run")
def run_reputation_decay(
    dry_run: bool = Query(default=True),
    request: Request = None,
    session: Session = Depends(get_session),
):
    """
    Run reputation decay for all inactive workers.

    Set dry_run=false to actually apply decay.
    """
    if not settings.feature_reputation_decay and not dry_run:
        raise HTTPException(400, "Reputation decay feature is disabled")

    results = run_decay_job(session, dry_run=dry_run)

    if not dry_run:
        log_audit(
            session,
            action="reputation_decay_manual",
            actor_type="admin",
            actor_id=None,
            target_type=None,
            target_id=None,
            details={
                "processed": results["processed"],
                "decayed": results["decayed"],
                "total_decay": float(results["total_decay"]),
            },
            request=request,
        )

    return results


@router.get("/reputation-decay/eligible")
def get_eligible_for_decay(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """
    Get workers who are eligible for reputation decay.
    """
    from datetime import timezone as tz

    now = datetime.now(tz.utc)
    grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)

    workers = session.exec(
        select(Worker)
        .where(and_(
            Worker.is_banned == False,
            Worker.reputation > MIN_REPUTATION,
            (Worker.last_task_at < grace_cutoff) | (Worker.last_task_at.is_(None)),
        ))
        .order_by(Worker.last_task_at.asc().nullsfirst())
        .limit(limit)
    ).all()

    return {
        "eligible_workers": [
            {
                "worker_id": w.id,
                "name": w.name,
                "reputation": float(w.reputation),
                "reputation_level": w.reputation_level,
                "last_task_at": w.last_task_at.isoformat() if w.last_task_at else None,
                "days_inactive": (now - (w.last_task_at or w.created_at)).days,
            }
            for w in workers
        ],
        "total_eligible": len(workers),
        "grace_period_days": GRACE_PERIOD_DAYS,
    }
