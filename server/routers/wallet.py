"""
Wallet and withdrawal management endpoints.
Handles balance operations, withdrawal requests, and payment processing.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
from sqlalchemy import and_

from ..db import get_session
from ..models import Worker, Transaction, WithdrawalRequest, AuditLog, AuditAction
from ..schemas import (
    WithdrawalRequest as WithdrawalRequestSchema,
    WithdrawalResponse,
    WithdrawalListResponse,
    SuccessResponse,
)
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wallet", tags=["Wallet"])


# =============================================================================
# HELPERS
# =============================================================================

def create_transaction(
    session: Session,
    worker: Worker,
    amount: Decimal,
    tx_type: str,
    description: str,
    task_id: int = None,
) -> Transaction:
    """Create transaction and update balance atomically."""
    balance_before = worker.balance
    worker.balance = worker.balance + amount

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


def log_audit(
    session: Session,
    action: str,
    actor_type: str,
    actor_id: Optional[int],
    target_type: Optional[str],
    target_id: Optional[int],
    details: dict,
) -> None:
    """Log audit event."""
    audit = AuditLog(
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    session.add(audit)


# =============================================================================
# BALANCE
# =============================================================================

@router.get("/balance/{worker_id}")
def get_balance(
    worker_id: int,
    session: Session = Depends(get_session),
):
    """Get worker's current balance and pending withdrawals."""
    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    # Get pending withdrawal total
    pending_total = session.exec(
        select(func.sum(WithdrawalRequest.amount))
        .where(and_(
            WithdrawalRequest.worker_id == worker_id,
            WithdrawalRequest.status == "pending"
        ))
    ).one() or Decimal("0.0")

    return {
        "worker_id": worker_id,
        "balance": float(worker.balance),
        "pending_balance": float(worker.pending_balance),
        "total_earned": float(worker.total_earned),
        "pending_withdrawals": float(pending_total),
        "available": float(worker.balance - pending_total),
    }


# =============================================================================
# WITHDRAWAL REQUEST
# =============================================================================

@router.post("/withdraw")
def request_withdrawal(
    worker_id: int,
    amount: Decimal,
    wallet_address: Optional[str] = None,
    payment_method: str = "internal",
    session: Session = Depends(get_session),
):
    """
    Create withdrawal request.

    - Validates sufficient balance
    - Checks minimum withdrawal amount
    - Creates hold transaction
    - Queues for admin approval
    """
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    if amount < settings.min_withdrawal:
        raise HTTPException(400, f"Minimum withdrawal: {settings.min_withdrawal}")

    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    if worker.is_banned:
        raise HTTPException(403, "Worker is banned")

    # Check pending withdrawals
    pending_total = session.exec(
        select(func.sum(WithdrawalRequest.amount))
        .where(and_(
            WithdrawalRequest.worker_id == worker_id,
            WithdrawalRequest.status == "pending"
        ))
    ).one() or Decimal("0.0")

    available = worker.balance - pending_total
    if amount > available:
        raise HTTPException(400, f"Insufficient funds. Available: {available}")

    # Create withdrawal request
    withdrawal = WithdrawalRequest(
        worker_id=worker_id,
        amount=amount,
        status="pending",
        wallet_address=wallet_address,
        payment_method=payment_method,
    )
    session.add(withdrawal)
    session.flush()  # Get ID

    # Create hold transaction
    create_transaction(
        session, worker, -amount, "hold",
        f"Hold for withdrawal #{withdrawal.id}"
    )

    # Audit log
    log_audit(
        session,
        action="withdrawal_request",
        actor_type="worker",
        actor_id=worker_id,
        target_type="withdrawal",
        target_id=withdrawal.id,
        details={"amount": float(amount), "method": payment_method},
    )

    session.add(worker)
    session.commit()

    logger.info(f"Withdrawal request #{withdrawal.id}: {amount} from worker {worker_id}")

    return {
        "status": "created",
        "withdrawal_id": withdrawal.id,
        "amount": float(amount),
    }


# =============================================================================
# LIST WITHDRAWALS
# =============================================================================

@router.get("/withdrawals")
def list_withdrawals(
    worker_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """List withdrawal requests with filtering."""
    query = select(WithdrawalRequest)
    count_query = select(func.count(WithdrawalRequest.id))

    if worker_id:
        query = query.where(WithdrawalRequest.worker_id == worker_id)
        count_query = count_query.where(WithdrawalRequest.worker_id == worker_id)

    if status:
        query = query.where(WithdrawalRequest.status == status)
        count_query = count_query.where(WithdrawalRequest.status == status)

    total = session.exec(count_query).one()

    offset = (page - 1) * page_size
    query = query.order_by(WithdrawalRequest.created_at.desc()).offset(offset).limit(page_size)
    withdrawals = session.exec(query).all()

    return {
        "withdrawals": [
            {
                "id": w.id,
                "uuid": w.uuid,
                "worker_id": w.worker_id,
                "amount": float(w.amount),
                "status": w.status,
                "wallet_address": w.wallet_address,
                "payment_method": w.payment_method,
                "rejection_reason": w.rejection_reason,
                "transaction_hash": w.transaction_hash,
                "created_at": w.created_at.isoformat(),
                "processed_at": w.processed_at.isoformat() if w.processed_at else None,
            }
            for w in withdrawals
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# =============================================================================
# WITHDRAWAL BY ID
# =============================================================================

@router.get("/withdrawals/{withdrawal_id}")
def get_withdrawal(
    withdrawal_id: int,
    session: Session = Depends(get_session),
):
    """Get withdrawal request details."""
    withdrawal = session.get(WithdrawalRequest, withdrawal_id)
    if not withdrawal:
        raise HTTPException(404, "Withdrawal not found")

    return {
        "id": withdrawal.id,
        "uuid": withdrawal.uuid,
        "worker_id": withdrawal.worker_id,
        "amount": float(withdrawal.amount),
        "status": withdrawal.status,
        "wallet_address": withdrawal.wallet_address,
        "payment_method": withdrawal.payment_method,
        "rejection_reason": withdrawal.rejection_reason,
        "transaction_hash": withdrawal.transaction_hash,
        "created_at": withdrawal.created_at.isoformat(),
        "processed_at": withdrawal.processed_at.isoformat() if withdrawal.processed_at else None,
    }


# =============================================================================
# APPROVE WITHDRAWAL (Admin)
# =============================================================================

@router.post("/approve/{withdrawal_id}")
def approve_withdrawal(
    withdrawal_id: int,
    transaction_hash: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """
    Approve withdrawal request (admin only).

    For crypto payments, include transaction_hash.
    """
    withdrawal = session.get(WithdrawalRequest, withdrawal_id)
    if not withdrawal:
        raise HTTPException(404, "Withdrawal not found")

    if withdrawal.status != "pending":
        raise HTTPException(400, f"Cannot approve: status is {withdrawal.status}")

    withdrawal.status = "approved"
    withdrawal.processed_at = datetime.now(timezone.utc)
    withdrawal.transaction_hash = transaction_hash

    log_audit(
        session,
        action="withdrawal_approved",
        actor_type="admin",
        actor_id=None,
        target_type="withdrawal",
        target_id=withdrawal_id,
        details={"amount": float(withdrawal.amount)},
    )

    session.add(withdrawal)
    session.commit()

    logger.info(f"Withdrawal #{withdrawal_id} approved")

    return {"status": "approved", "withdrawal_id": withdrawal_id}


# =============================================================================
# REJECT WITHDRAWAL (Admin)
# =============================================================================

@router.post("/reject/{withdrawal_id}")
def reject_withdrawal(
    withdrawal_id: int,
    reason: str,
    session: Session = Depends(get_session),
):
    """
    Reject withdrawal and refund balance.

    Reason is required for audit trail.
    """
    if not reason:
        raise HTTPException(400, "Reason required")

    withdrawal = session.get(WithdrawalRequest, withdrawal_id)
    if not withdrawal:
        raise HTTPException(404, "Withdrawal not found")

    if withdrawal.status != "pending":
        raise HTTPException(400, f"Cannot reject: status is {withdrawal.status}")

    worker = session.get(Worker, withdrawal.worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    # Refund balance
    create_transaction(
        session, worker, withdrawal.amount, "refund",
        f"Refund withdrawal #{withdrawal_id}: {reason}"
    )

    withdrawal.status = "rejected"
    withdrawal.rejection_reason = reason
    withdrawal.processed_at = datetime.now(timezone.utc)

    log_audit(
        session,
        action="withdrawal_rejected",
        actor_type="admin",
        actor_id=None,
        target_type="withdrawal",
        target_id=withdrawal_id,
        details={"amount": float(withdrawal.amount), "reason": reason},
    )

    session.add_all([withdrawal, worker])
    session.commit()

    logger.info(f"Withdrawal #{withdrawal_id} rejected: {reason}")

    return {"status": "rejected", "withdrawal_id": withdrawal_id}


# =============================================================================
# MARK AS PAID (Admin)
# =============================================================================

@router.post("/paid/{withdrawal_id}")
def mark_paid(
    withdrawal_id: int,
    transaction_hash: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Mark approved withdrawal as paid."""
    withdrawal = session.get(WithdrawalRequest, withdrawal_id)
    if not withdrawal:
        raise HTTPException(404, "Withdrawal not found")

    if withdrawal.status != "approved":
        raise HTTPException(400, f"Cannot mark paid: status is {withdrawal.status}")

    withdrawal.status = "paid"
    withdrawal.processed_at = datetime.now(timezone.utc)
    if transaction_hash:
        withdrawal.transaction_hash = transaction_hash

    log_audit(
        session,
        action="withdrawal_paid",
        actor_type="admin",
        actor_id=None,
        target_type="withdrawal",
        target_id=withdrawal_id,
        details={
            "amount": float(withdrawal.amount),
            "tx_hash": transaction_hash,
        },
    )

    session.add(withdrawal)
    session.commit()

    logger.info(f"Withdrawal #{withdrawal_id} marked as paid")

    return {"status": "paid", "withdrawal_id": withdrawal_id}


# =============================================================================
# CANCEL WITHDRAWAL (Worker)
# =============================================================================

@router.post("/cancel/{withdrawal_id}")
def cancel_withdrawal(
    withdrawal_id: int,
    worker_id: int,
    session: Session = Depends(get_session),
):
    """
    Cancel pending withdrawal request.

    Only the requesting worker can cancel.
    """
    withdrawal = session.get(WithdrawalRequest, withdrawal_id)
    if not withdrawal:
        raise HTTPException(404, "Withdrawal not found")

    if withdrawal.worker_id != worker_id:
        raise HTTPException(403, "Not your withdrawal")

    if withdrawal.status != "pending":
        raise HTTPException(400, f"Cannot cancel: status is {withdrawal.status}")

    worker = session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(404, "Worker not found")

    # Refund balance
    create_transaction(
        session, worker, withdrawal.amount, "refund",
        f"Cancelled withdrawal #{withdrawal_id}"
    )

    withdrawal.status = "cancelled"
    withdrawal.processed_at = datetime.now(timezone.utc)

    log_audit(
        session,
        action="withdrawal_cancelled",
        actor_type="worker",
        actor_id=worker_id,
        target_type="withdrawal",
        target_id=withdrawal_id,
        details={"amount": float(withdrawal.amount)},
    )

    session.add_all([withdrawal, worker])
    session.commit()

    logger.info(f"Withdrawal #{withdrawal_id} cancelled by worker {worker_id}")

    return {"status": "cancelled", "withdrawal_id": withdrawal_id}


# =============================================================================
# STATS
# =============================================================================

@router.get("/stats")
def get_wallet_stats(session: Session = Depends(get_session)):
    """Get withdrawal statistics."""
    stats = {}
    for status in ["pending", "approved", "rejected", "paid", "cancelled"]:
        count = session.exec(
            select(func.count(WithdrawalRequest.id))
            .where(WithdrawalRequest.status == status)
        ).one()
        total = session.exec(
            select(func.sum(WithdrawalRequest.amount))
            .where(WithdrawalRequest.status == status)
        ).one() or Decimal("0.0")
        stats[status] = {"count": count, "total": float(total)}

    return {"stats": stats}
