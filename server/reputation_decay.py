"""
Reputation Decay System for Distributed AI Network.

Implements reputation decay for inactive workers:
- Workers who don't complete tasks lose reputation over time
- Decay rate varies by reputation tier (higher tiers decay slower)
- Grace period before decay begins
- Reactivation bonus for returning workers
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Tuple

from sqlmodel import Session, select, and_

from .models import Worker, ReputationHistory, AuditLog
from .config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# DECAY CONFIGURATION
# =============================================================================

# Grace period (days without activity before decay starts)
GRACE_PERIOD_DAYS = 7

# Decay rates per day by reputation level (higher tiers decay slower)
DECAY_RATES = {
    "bronze": Decimal("0.02"),   # 0.02/day = ~0.6/month
    "silver": Decimal("0.015"),  # 0.015/day = ~0.45/month
    "gold": Decimal("0.01"),     # 0.01/day = ~0.3/month
    "platinum": Decimal("0.005"),# 0.005/day = ~0.15/month
    "diamond": Decimal("0.002"), # 0.002/day = ~0.06/month
}

# Minimum reputation (never decay below this)
MIN_REPUTATION = Decimal("0.5")

# Reactivation bonus (percentage of lost reputation restored)
REACTIVATION_BONUS_PERCENT = 0.25

# Maximum decay per run (prevents massive drops if job hasn't run in a while)
MAX_DECAY_PER_RUN = Decimal("0.5")


# =============================================================================
# CORE DECAY FUNCTIONS
# =============================================================================

def calculate_decay(
    worker: Worker,
    days_inactive: int,
) -> Decimal:
    """
    Calculate reputation decay amount for a worker.

    Args:
        worker: The worker to calculate decay for
        days_inactive: Days since last task completion

    Returns:
        Amount to decay (positive value)
    """
    # Apply grace period
    decay_days = max(0, days_inactive - GRACE_PERIOD_DAYS)

    if decay_days <= 0:
        return Decimal("0")

    # Get decay rate for this tier
    decay_rate = DECAY_RATES.get(
        worker.reputation_level,
        DECAY_RATES["bronze"]
    )

    # Calculate total decay
    total_decay = decay_rate * decay_days

    # Cap at maximum
    total_decay = min(total_decay, MAX_DECAY_PER_RUN)

    # Don't decay below minimum
    current_above_min = worker.reputation - MIN_REPUTATION
    if current_above_min <= 0:
        return Decimal("0")

    return min(total_decay, current_above_min)


def apply_decay(
    session: Session,
    worker: Worker,
    decay_amount: Decimal,
    reason: str = "Inactivity decay",
) -> None:
    """
    Apply reputation decay to a worker.

    Args:
        session: Database session
        worker: Worker to apply decay to
        decay_amount: Amount to subtract from reputation
        reason: Reason for the decay
    """
    if decay_amount <= 0:
        return

    old_reputation = worker.reputation
    new_reputation = max(MIN_REPUTATION, worker.reputation - decay_amount)

    worker.reputation = new_reputation

    # Update reputation level
    rep = float(new_reputation)
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

    worker.updated_at = datetime.now(timezone.utc)

    # Log history
    history = ReputationHistory(
        worker_id=worker.id,
        old_reputation=old_reputation,
        new_reputation=new_reputation,
        change_amount=-decay_amount,
        reason=reason,
    )
    session.add(history)
    session.add(worker)


def apply_reactivation_bonus(
    session: Session,
    worker: Worker,
) -> Decimal:
    """
    Apply reactivation bonus when an inactive worker completes a task.

    This restores some of the lost reputation to encourage workers
    to come back after being inactive.

    Args:
        session: Database session
        worker: Worker who just completed a task

    Returns:
        Bonus amount applied
    """
    # Find decay history in the last 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    decay_history = session.exec(
        select(ReputationHistory)
        .where(and_(
            ReputationHistory.worker_id == worker.id,
            ReputationHistory.change_amount < 0,
            ReputationHistory.reason.contains("decay"),
            ReputationHistory.created_at >= cutoff,
        ))
    ).all()

    if not decay_history:
        return Decimal("0")

    # Calculate total decay
    total_decay = sum(abs(h.change_amount) for h in decay_history)

    # Calculate bonus
    bonus = total_decay * Decimal(str(REACTIVATION_BONUS_PERCENT))

    if bonus <= 0:
        return Decimal("0")

    # Apply bonus (capped at max reputation)
    old_reputation = worker.reputation
    new_reputation = min(Decimal("10.0"), worker.reputation + bonus)
    actual_bonus = new_reputation - old_reputation

    if actual_bonus > 0:
        worker.reputation = new_reputation

        # Update level
        rep = float(new_reputation)
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
            old_reputation=old_reputation,
            new_reputation=new_reputation,
            change_amount=actual_bonus,
            reason="Reactivation bonus",
        )
        session.add(history)
        session.add(worker)

        logger.info(
            f"Applied reactivation bonus to worker {worker.id}: "
            f"+{actual_bonus} (from {old_reputation} to {new_reputation})"
        )

    return actual_bonus


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def run_decay_job(
    session: Session,
    dry_run: bool = False,
) -> Dict:
    """
    Run reputation decay for all eligible workers.

    Args:
        session: Database session
        dry_run: If True, don't actually apply changes

    Returns:
        Summary of decay operations
    """
    now = datetime.now(timezone.utc)
    grace_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)

    # Find inactive workers (not banned, not seen recently)
    workers = session.exec(
        select(Worker)
        .where(and_(
            Worker.is_banned == False,
            Worker.reputation > MIN_REPUTATION,
            # Last task was before grace period
            (Worker.last_task_at < grace_cutoff) | (Worker.last_task_at.is_(None)),
        ))
    ).all()

    results = {
        "processed": 0,
        "decayed": 0,
        "total_decay": Decimal("0"),
        "workers": [],
        "dry_run": dry_run,
    }

    for worker in workers:
        # Calculate days since last task
        if worker.last_task_at:
            days_inactive = (now - worker.last_task_at).days
        else:
            # Never did a task - use created_at
            days_inactive = (now - worker.created_at).days

        decay = calculate_decay(worker, days_inactive)

        results["processed"] += 1

        if decay > 0:
            results["decayed"] += 1
            results["total_decay"] += decay
            results["workers"].append({
                "worker_id": worker.id,
                "name": worker.name,
                "days_inactive": days_inactive,
                "old_reputation": float(worker.reputation),
                "decay_amount": float(decay),
                "new_reputation": float(worker.reputation - decay),
            })

            if not dry_run:
                apply_decay(
                    session,
                    worker,
                    decay,
                    f"Inactivity decay ({days_inactive} days inactive)"
                )

    if not dry_run:
        # Log audit
        audit = AuditLog(
            action="reputation_decay_job",
            actor_type="system",
            actor_id=None,
            target_type=None,
            target_id=None,
            details={
                "processed": results["processed"],
                "decayed": results["decayed"],
                "total_decay": float(results["total_decay"]),
            },
        )
        session.add(audit)
        session.commit()

        logger.info(
            f"Reputation decay job completed: "
            f"{results['decayed']}/{results['processed']} workers decayed, "
            f"total decay: {results['total_decay']}"
        )

    return results


def get_decay_preview(
    session: Session,
    worker_id: int,
) -> Dict:
    """
    Preview what decay would be applied to a specific worker.

    Args:
        session: Database session
        worker_id: Worker to check

    Returns:
        Decay preview information
    """
    worker = session.get(Worker, worker_id)
    if not worker:
        return {"error": "Worker not found"}

    now = datetime.now(timezone.utc)

    if worker.last_task_at:
        days_inactive = (now - worker.last_task_at).days
        last_task = worker.last_task_at.isoformat()
    else:
        days_inactive = (now - worker.created_at).days
        last_task = None

    decay = calculate_decay(worker, days_inactive)
    decay_rate = DECAY_RATES.get(worker.reputation_level, DECAY_RATES["bronze"])

    return {
        "worker_id": worker_id,
        "name": worker.name,
        "current_reputation": float(worker.reputation),
        "reputation_level": worker.reputation_level,
        "last_task_at": last_task,
        "days_inactive": days_inactive,
        "grace_period_days": GRACE_PERIOD_DAYS,
        "in_grace_period": days_inactive <= GRACE_PERIOD_DAYS,
        "daily_decay_rate": float(decay_rate),
        "pending_decay": float(decay),
        "reputation_after_decay": float(worker.reputation - decay),
        "minimum_reputation": float(MIN_REPUTATION),
    }
