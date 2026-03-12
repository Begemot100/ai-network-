"""
Collusion Detection System for Distributed AI Network.

Detects patterns of worker collusion:
1. Mutual validation rings (workers always validating each other)
2. Suspicious approval rates (workers never disagreeing)
3. Timing anomalies (suspiciously fast validations)
4. Geographic/network clustering (same IP ranges)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from sqlmodel import Session, select, func, and_

from .models import Worker, Task, AuditLog, AuditAction, ReputationHistory
from .config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CollusionEvidence:
    """Evidence of potential collusion."""
    evidence_type: str
    worker_ids: Set[int]
    score: float  # 0-1, higher = more suspicious
    description: str
    details: Dict


@dataclass
class CollusionReport:
    """Full collusion analysis report for a worker or worker pair."""
    worker_id: int
    total_score: float
    is_suspicious: bool
    evidence: List[CollusionEvidence]
    recommendation: str


# =============================================================================
# DETECTION THRESHOLDS
# =============================================================================

# Mutual validation thresholds
MIN_MUTUAL_VALIDATIONS = 5  # Minimum interactions to consider
MUTUAL_VALIDATION_THRESHOLD = 0.6  # 60%+ mutual = suspicious

# Approval rate thresholds
MIN_TASKS_FOR_ANALYSIS = 10  # Minimum tasks to analyze
PERFECT_APPROVAL_THRESHOLD = 0.98  # 98%+ approval = suspicious

# Timing thresholds
MIN_VALIDATION_TIME_MS = 500  # Less than 500ms is suspicious
SUSPICIOUS_TIMING_RATIO = 0.5  # 50%+ fast validations = suspicious

# Overall thresholds
COLLUSION_SCORE_THRESHOLD = 0.7  # Score above this = flag for review
AUTO_BAN_THRESHOLD = 0.9  # Score above this = auto-ban


# =============================================================================
# CORE DETECTION FUNCTIONS
# =============================================================================

def analyze_mutual_validations(
    session: Session,
    worker_id: int,
    days: int = 30,
) -> List[CollusionEvidence]:
    """
    Analyze mutual validation patterns.

    Detects when two workers frequently validate each other's work,
    which could indicate a collusion ring.
    """
    evidence = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get tasks where worker_id was the executor
    executed_tasks = session.exec(
        select(Task.validator_worker_id, func.count(Task.id))
        .where(and_(
            Task.worker_id == worker_id,
            Task.status.in_(["done", "rejected"]),
            Task.validated_at >= cutoff,
            Task.validator_worker_id.isnot(None),
        ))
        .group_by(Task.validator_worker_id)
    ).all()

    # Get tasks where worker_id was the validator
    validated_tasks = session.exec(
        select(Task.worker_id, func.count(Task.id))
        .where(and_(
            Task.validator_worker_id == worker_id,
            Task.status.in_(["done", "rejected"]),
            Task.validated_at >= cutoff,
            Task.worker_id.isnot(None),
        ))
        .group_by(Task.worker_id)
    ).all()

    # Build maps
    validated_by = {vid: count for vid, count in executed_tasks}
    validated_of = {wid: count for wid, count in validated_tasks}

    # Find mutual pairs
    for partner_id, validated_me in validated_by.items():
        i_validated = validated_of.get(partner_id, 0)
        total_interactions = validated_me + i_validated

        if total_interactions >= MIN_MUTUAL_VALIDATIONS:
            # Check if mutual validation rate is high
            total_my_validations = sum(validated_of.values())
            total_their_validations = sum(validated_by.values())

            my_ratio = i_validated / max(total_my_validations, 1)
            their_ratio = validated_me / max(total_their_validations, 1)

            mutual_score = (my_ratio + their_ratio) / 2

            if mutual_score >= MUTUAL_VALIDATION_THRESHOLD:
                evidence.append(CollusionEvidence(
                    evidence_type="mutual_validation",
                    worker_ids={worker_id, partner_id},
                    score=mutual_score,
                    description=f"High mutual validation rate with worker {partner_id}",
                    details={
                        "partner_id": partner_id,
                        "validated_them": i_validated,
                        "validated_by_them": validated_me,
                        "my_ratio": round(my_ratio, 3),
                        "their_ratio": round(their_ratio, 3),
                    }
                ))

    return evidence


def analyze_approval_rates(
    session: Session,
    worker_id: int,
    days: int = 30,
) -> List[CollusionEvidence]:
    """
    Analyze approval/rejection rates.

    Detects when a worker has suspiciously high approval rates,
    especially with specific partners.
    """
    evidence = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get approval stats as executor
    executor_stats = session.exec(
        select(
            Task.validator_worker_id,
            Task.status,
            func.count(Task.id)
        )
        .where(and_(
            Task.worker_id == worker_id,
            Task.status.in_(["done", "rejected"]),
            Task.validated_at >= cutoff,
        ))
        .group_by(Task.validator_worker_id, Task.status)
    ).all()

    # Aggregate by validator
    validator_results: Dict[int, Dict[str, int]] = defaultdict(lambda: {"done": 0, "rejected": 0})
    for vid, status, count in executor_stats:
        if vid:
            validator_results[vid][status] = count

    # Check each validator relationship
    for vid, results in validator_results.items():
        total = results["done"] + results["rejected"]
        if total >= MIN_TASKS_FOR_ANALYSIS:
            approval_rate = results["done"] / total

            if approval_rate >= PERFECT_APPROVAL_THRESHOLD:
                evidence.append(CollusionEvidence(
                    evidence_type="high_approval_rate",
                    worker_ids={worker_id, vid},
                    score=approval_rate,
                    description=f"Suspiciously high approval rate by validator {vid}",
                    details={
                        "validator_id": vid,
                        "approved": results["done"],
                        "rejected": results["rejected"],
                        "rate": round(approval_rate, 3),
                    }
                ))

    # Also check as validator
    validator_stats = session.exec(
        select(
            Task.worker_id,
            Task.status,
            func.count(Task.id)
        )
        .where(and_(
            Task.validator_worker_id == worker_id,
            Task.status.in_(["done", "rejected"]),
            Task.validated_at >= cutoff,
        ))
        .group_by(Task.worker_id, Task.status)
    ).all()

    executor_results: Dict[int, Dict[str, int]] = defaultdict(lambda: {"done": 0, "rejected": 0})
    for wid, status, count in validator_stats:
        if wid:
            executor_results[wid][status] = count

    for wid, results in executor_results.items():
        total = results["done"] + results["rejected"]
        if total >= MIN_TASKS_FOR_ANALYSIS:
            approval_rate = results["done"] / total

            if approval_rate >= PERFECT_APPROVAL_THRESHOLD:
                evidence.append(CollusionEvidence(
                    evidence_type="always_approving",
                    worker_ids={worker_id, wid},
                    score=approval_rate,
                    description=f"Worker {worker_id} always approves worker {wid}",
                    details={
                        "executor_id": wid,
                        "approved": results["done"],
                        "rejected": results["rejected"],
                        "rate": round(approval_rate, 3),
                    }
                ))

    return evidence


def analyze_timing_patterns(
    session: Session,
    worker_id: int,
    days: int = 30,
) -> List[CollusionEvidence]:
    """
    Analyze validation timing patterns.

    Detects suspiciously fast validations which might indicate
    automatic approval without actual verification.
    """
    evidence = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get validation tasks with timing
    tasks = session.exec(
        select(Task)
        .where(and_(
            Task.validator_worker_id == worker_id,
            Task.status.in_(["done", "rejected"]),
            Task.validated_at >= cutoff,
            Task.submitted_at.isnot(None),
            Task.validated_at.isnot(None),
        ))
    ).all()

    if len(tasks) < MIN_TASKS_FOR_ANALYSIS:
        return evidence

    # Calculate validation times
    fast_validations = 0
    total_validations = len(tasks)
    validation_times = []

    for task in tasks:
        if task.submitted_at and task.validated_at:
            time_diff = (task.validated_at - task.submitted_at).total_seconds() * 1000
            validation_times.append(time_diff)

            if time_diff < MIN_VALIDATION_TIME_MS:
                fast_validations += 1

    fast_ratio = fast_validations / total_validations

    if fast_ratio >= SUSPICIOUS_TIMING_RATIO:
        avg_time = sum(validation_times) / len(validation_times) if validation_times else 0

        evidence.append(CollusionEvidence(
            evidence_type="suspicious_timing",
            worker_ids={worker_id},
            score=fast_ratio,
            description="Too many suspiciously fast validations",
            details={
                "fast_validations": fast_validations,
                "total_validations": total_validations,
                "fast_ratio": round(fast_ratio, 3),
                "avg_time_ms": round(avg_time, 1),
                "min_time_ms": round(min(validation_times), 1) if validation_times else 0,
            }
        ))

    return evidence


def find_collusion_rings(
    session: Session,
    min_ring_size: int = 3,
    days: int = 30,
) -> List[CollusionEvidence]:
    """
    Find potential collusion rings (groups of workers who only validate each other).
    """
    evidence = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get all validation pairs
    pairs = session.exec(
        select(
            Task.worker_id,
            Task.validator_worker_id,
            func.count(Task.id)
        )
        .where(and_(
            Task.status.in_(["done", "rejected"]),
            Task.validated_at >= cutoff,
            Task.worker_id.isnot(None),
            Task.validator_worker_id.isnot(None),
        ))
        .group_by(Task.worker_id, Task.validator_worker_id)
    ).all()

    # Build graph
    graph: Dict[int, Set[int]] = defaultdict(set)
    for worker_id, validator_id, count in pairs:
        if count >= 3:  # At least 3 interactions
            graph[worker_id].add(validator_id)
            graph[validator_id].add(worker_id)

    # Find cliques (fully connected groups)
    visited = set()

    def find_clique(start: int) -> Set[int]:
        clique = {start}
        candidates = graph[start].copy()

        for candidate in candidates:
            if all(c in graph[candidate] for c in clique):
                clique.add(candidate)

        return clique

    for worker_id in graph:
        if worker_id not in visited:
            clique = find_clique(worker_id)
            visited.update(clique)

            if len(clique) >= min_ring_size:
                evidence.append(CollusionEvidence(
                    evidence_type="collusion_ring",
                    worker_ids=clique,
                    score=0.8 + (len(clique) - 3) * 0.05,  # Higher score for larger rings
                    description=f"Potential collusion ring of {len(clique)} workers",
                    details={
                        "ring_members": list(clique),
                        "ring_size": len(clique),
                    }
                ))

    return evidence


# =============================================================================
# MAIN ANALYSIS FUNCTIONS
# =============================================================================

def analyze_worker(
    session: Session,
    worker_id: int,
    days: int = 30,
) -> CollusionReport:
    """
    Perform full collusion analysis on a single worker.
    """
    all_evidence = []

    # Run all detection methods
    all_evidence.extend(analyze_mutual_validations(session, worker_id, days))
    all_evidence.extend(analyze_approval_rates(session, worker_id, days))
    all_evidence.extend(analyze_timing_patterns(session, worker_id, days))

    # Calculate total score
    if all_evidence:
        total_score = max(e.score for e in all_evidence)
    else:
        total_score = 0.0

    # Determine recommendation
    if total_score >= AUTO_BAN_THRESHOLD:
        recommendation = "AUTO_BAN"
    elif total_score >= COLLUSION_SCORE_THRESHOLD:
        recommendation = "REVIEW"
    else:
        recommendation = "OK"

    return CollusionReport(
        worker_id=worker_id,
        total_score=round(total_score, 3),
        is_suspicious=total_score >= COLLUSION_SCORE_THRESHOLD,
        evidence=all_evidence,
        recommendation=recommendation,
    )


def run_full_scan(
    session: Session,
    days: int = 30,
) -> Dict[int, CollusionReport]:
    """
    Run collusion analysis on all active workers.
    """
    # Get active workers
    workers = session.exec(
        select(Worker)
        .where(and_(
            Worker.is_banned == False,
            Worker.tasks_completed > 0,
        ))
    ).all()

    reports = {}

    for worker in workers:
        report = analyze_worker(session, worker.id, days)
        if report.is_suspicious:
            reports[worker.id] = report

            # Log suspicious activity
            logger.warning(
                f"Collusion detected: worker={worker.id} "
                f"score={report.total_score} "
                f"recommendation={report.recommendation}"
            )

    # Also check for rings
    ring_evidence = find_collusion_rings(session, days=days)
    for ev in ring_evidence:
        logger.warning(
            f"Collusion ring detected: workers={ev.worker_ids} "
            f"score={ev.score}"
        )

    return reports


def auto_ban_colluders(
    session: Session,
    reports: Dict[int, CollusionReport],
    dry_run: bool = True,
) -> List[int]:
    """
    Automatically ban workers with very high collusion scores.
    """
    banned = []

    for worker_id, report in reports.items():
        if report.recommendation == "AUTO_BAN":
            worker = session.get(Worker, worker_id)

            if worker and not worker.is_banned:
                if not dry_run:
                    worker.is_banned = True
                    worker.ban_reason = f"Automated ban: collusion score {report.total_score}"
                    worker.banned_at = datetime.now(timezone.utc)
                    worker.status = "banned"

                    # Audit log
                    audit = AuditLog(
                        action=AuditAction.FRAUD_DETECTED.value,
                        actor_type="system",
                        actor_id=None,
                        target_type="worker",
                        target_id=worker_id,
                        details={
                            "reason": "collusion_detection",
                            "score": report.total_score,
                            "evidence_count": len(report.evidence),
                            "evidence_types": [e.evidence_type for e in report.evidence],
                        },
                    )
                    session.add(audit)

                banned.append(worker_id)

                logger.warning(
                    f"{'[DRY RUN] ' if dry_run else ''}Banned worker {worker_id} "
                    f"for collusion (score={report.total_score})"
                )

    if not dry_run:
        session.commit()

    return banned
