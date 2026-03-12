"""
SQLModel database models for the Distributed AI Network.
Production-grade models with proper relationships and validation.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Text, Index, JSON
import uuid


def utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# ENUMS
# =============================================================================

class WorkerStatus(str, Enum):
    IDLE = "idle"
    ONLINE = "online"
    WORKING = "working"
    OFFLINE = "offline"
    BANNED = "banned"


class ReputationLevel(str, Enum):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    SUBMITTED_A = "submitted_A"
    VALIDATING = "validating"
    DONE = "done"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    TEXT = "text"
    REVERSE = "reverse"
    MATH = "math"
    LLM = "llm"
    HEAVY = "heavy"
    SENTIMENT = "sentiment"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"


class TransactionType(str, Enum):
    REWARD = "reward"
    PENALTY = "penalty"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    BONUS = "bonus"
    CLAWBACK = "clawback"


class WithdrawalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"
    CANCELLED = "cancelled"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditAction(str, Enum):
    WORKER_REGISTER = "worker_register"
    WORKER_BAN = "worker_ban"
    WORKER_UNBAN = "worker_unban"
    TASK_CREATE = "task_create"
    TASK_ASSIGN = "task_assign"
    TASK_SUBMIT = "task_submit"
    TASK_VALIDATE = "task_validate"
    TASK_EXPIRE = "task_expire"
    JOB_CREATE = "job_create"
    JOB_COMPLETE = "job_complete"
    JOB_FAIL = "job_fail"
    JOB_CANCEL = "job_cancel"
    WITHDRAWAL_REQUEST = "withdrawal_request"
    WITHDRAWAL_APPROVE = "withdrawal_approve"
    WITHDRAWAL_REJECT = "withdrawal_reject"
    FRAUD_DETECTED = "fraud_detected"
    REPUTATION_UPDATE = "reputation_update"


# =============================================================================
# WORKER MODEL
# =============================================================================

class Worker(SQLModel, table=True):
    """Worker model representing a compute node in the network."""

    __tablename__ = "workers"

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Identity
    name: str = Field(max_length=255)
    fingerprint: Optional[str] = Field(default=None, max_length=512)

    # Capabilities
    power: int = Field(default=1, ge=1, le=100)
    capabilities: str = Field(default="text", max_length=255)
    worker_type: str = Field(default="general", max_length=50)

    # Economy
    balance: Decimal = Field(default=Decimal("0.0"), ge=0)
    pending_balance: Decimal = Field(default=Decimal("0.0"), ge=0)
    total_earned: Decimal = Field(default=Decimal("0.0"))
    total_withdrawn: Decimal = Field(default=Decimal("0.0"))

    # Reputation
    reputation: Decimal = Field(default=Decimal("1.0"))
    reputation_level: str = Field(default=ReputationLevel.BRONZE.value)

    # Statistics
    tasks_completed: int = Field(default=0)
    tasks_failed: int = Field(default=0)
    validations_completed: int = Field(default=0)
    validations_failed: int = Field(default=0)
    golden_tasks_passed: int = Field(default=0)
    golden_tasks_failed: int = Field(default=0)

    # Status
    status: str = Field(default=WorkerStatus.IDLE.value)
    is_banned: bool = Field(default=False)
    ban_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    banned_at: Optional[datetime] = Field(default=None)

    # Timestamps
    last_seen: datetime = Field(default_factory=utc_now)
    last_task_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    tasks: List["Task"] = Relationship(
        back_populates="worker",
        sa_relationship_kwargs={"foreign_keys": "[Task.worker_id]"}
    )
    validated_tasks: List["Task"] = Relationship(
        back_populates="validator",
        sa_relationship_kwargs={"foreign_keys": "[Task.validator_worker_id]"}
    )
    transactions: List["Transaction"] = Relationship(back_populates="worker")
    withdrawal_requests: List["WithdrawalRequest"] = Relationship(
        back_populates="worker",
        sa_relationship_kwargs={"foreign_keys": "[WithdrawalRequest.worker_id]"}
    )

    @property
    def success_rate(self) -> float:
        """Calculate task success rate."""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.0
        return round(self.tasks_completed / total * 100, 2)

    def update_reputation_level(self) -> None:
        """Update reputation level based on reputation score."""
        rep = float(self.reputation)
        if rep >= 5.0:
            self.reputation_level = ReputationLevel.DIAMOND.value
        elif rep >= 3.0:
            self.reputation_level = ReputationLevel.PLATINUM.value
        elif rep >= 2.0:
            self.reputation_level = ReputationLevel.GOLD.value
        elif rep >= 1.5:
            self.reputation_level = ReputationLevel.SILVER.value
        else:
            self.reputation_level = ReputationLevel.BRONZE.value


# =============================================================================
# TASK MODEL
# =============================================================================

class Task(SQLModel, table=True):
    """Task model representing a unit of work."""

    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    # Task definition
    prompt: str = Field(sa_column=Column(Text, nullable=False))
    task_type: str = Field(default=TaskType.TEXT.value, max_length=50)
    priority: int = Field(default=0)
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    is_golden: bool = Field(default=False)
    golden_answer: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Status
    status: str = Field(default=TaskStatus.PENDING.value, index=True)

    # Worker A (executor)
    worker_id: Optional[int] = Field(default=None, foreign_key="workers.id")
    result: Optional[str] = Field(default=None, sa_column=Column(Text))
    result_hash: Optional[str] = Field(default=None, max_length=64)
    submitted_at: Optional[datetime] = Field(default=None)

    # Worker B (validator)
    validator_worker_id: Optional[int] = Field(default=None, foreign_key="workers.id")
    validator_result: Optional[str] = Field(default=None, sa_column=Column(Text))
    validator_result_hash: Optional[str] = Field(default=None, max_length=64)
    validated_at: Optional[datetime] = Field(default=None)

    # Validation
    validation_attempts: int = Field(default=0)
    max_validation_attempts: int = Field(default=3)
    confidence: Decimal = Field(default=Decimal("0.0"))

    # Rewards
    reward_worker_a: Optional[Decimal] = Field(default=None)
    reward_worker_b: Optional[Decimal] = Field(default=None)

    # Job reference
    job_id: Optional[str] = Field(default=None, max_length=36, index=True)
    chunk_id: Optional[int] = Field(default=None)

    # Lease management
    lease_expires_at: Optional[datetime] = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    worker: Optional[Worker] = Relationship(
        back_populates="tasks",
        sa_relationship_kwargs={"foreign_keys": "[Task.worker_id]"}
    )
    validator: Optional[Worker] = Relationship(
        back_populates="validated_tasks",
        sa_relationship_kwargs={"foreign_keys": "[Task.validator_worker_id]"}
    )


# =============================================================================
# TRANSACTION MODEL
# =============================================================================

class Transaction(SQLModel, table=True):
    """Transaction model for tracking all financial operations."""

    __tablename__ = "transactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    worker_id: int = Field(foreign_key="workers.id")

    # Transaction details
    type: str = Field(max_length=50)
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal

    # Reference
    task_id: Optional[int] = Field(default=None, foreign_key="tasks.id")
    description: str = Field(sa_column=Column(Text, nullable=False))
    extra_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)

    # Relationships
    worker: Optional[Worker] = Relationship(back_populates="transactions")


# =============================================================================
# WITHDRAWAL REQUEST MODEL
# =============================================================================

class WithdrawalRequest(SQLModel, table=True):
    """Withdrawal request model."""

    __tablename__ = "withdrawal_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()), unique=True, index=True)

    worker_id: int = Field(foreign_key="workers.id")

    amount: Decimal = Field(gt=0)
    wallet_address: Optional[str] = Field(default=None, max_length=255)
    payment_method: str = Field(default="internal", max_length=50)

    status: str = Field(default=WithdrawalStatus.PENDING.value)

    # Admin handling
    processed_by: Optional[int] = Field(default=None, foreign_key="workers.id")
    processed_at: Optional[datetime] = Field(default=None)
    rejection_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    transaction_hash: Optional[str] = Field(default=None, max_length=255)

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    worker: Optional[Worker] = Relationship(
        back_populates="withdrawal_requests",
        sa_relationship_kwargs={"foreign_keys": "[WithdrawalRequest.worker_id]"}
    )


# =============================================================================
# JOB MODEL (Kafka pipeline)
# =============================================================================

class Job(SQLModel, table=True):
    """Job model for Kafka pipeline tracking."""

    __tablename__ = "ai_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True, max_length=36)

    # Job definition
    job_type: str = Field(default="sentiment_analysis", max_length=50)
    source_file: Optional[str] = Field(default=None, max_length=255)

    # Progress
    total_chunks: int = Field(default=0)
    completed_chunks: int = Field(default=0)
    failed_chunks: int = Field(default=0)

    # Status
    status: str = Field(default=JobStatus.PENDING.value)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Results
    result_summary: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    # Timestamps
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def progress_percent(self) -> float:
        """Calculate job progress percentage."""
        if self.total_chunks == 0:
            return 0.0
        return round(self.completed_chunks / self.total_chunks * 100, 2)


# =============================================================================
# JOB RESULT MODEL
# =============================================================================

class JobResult(SQLModel, table=True):
    """Individual chunk result for a job."""

    __tablename__ = "ai_results"

    id: Optional[int] = Field(default=None, primary_key=True)

    job_id: str = Field(foreign_key="ai_jobs.job_id", index=True)
    chunk_id: int

    # Result
    result: dict = Field(sa_column=Column(JSON, nullable=False))
    worker_type: Optional[str] = Field(default=None, max_length=50)
    processing_time_ms: Optional[int] = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)


# =============================================================================
# JOB EVENT MODEL
# =============================================================================

class JobEvent(SQLModel, table=True):
    """Job event for WebSocket streaming."""

    __tablename__ = "ai_job_events"

    id: Optional[int] = Field(default=None, primary_key=True)

    job_id: str = Field(foreign_key="ai_jobs.job_id", index=True)

    event_type: str = Field(max_length=50)
    chunk_id: Optional[int] = Field(default=None)
    extra_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=utc_now)


# =============================================================================
# AUDIT LOG MODEL
# =============================================================================

class AuditLog(SQLModel, table=True):
    """Audit log for tracking all system events."""

    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Action
    action: str = Field(max_length=50)

    # Actor
    actor_type: str = Field(max_length=50)  # 'worker', 'system', 'admin'
    actor_id: Optional[int] = Field(default=None)

    # Target
    target_type: Optional[str] = Field(default=None, max_length=50)
    target_id: Optional[int] = Field(default=None)

    # Details
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)


# =============================================================================
# GOLDEN TASK MODEL
# =============================================================================

class GoldenTask(SQLModel, table=True):
    """Golden task (honeypot) for fraud detection."""

    __tablename__ = "golden_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)

    prompt: str = Field(sa_column=Column(Text, nullable=False))
    task_type: str = Field(max_length=50)
    expected_answer: str = Field(sa_column=Column(Text, nullable=False))

    # Usage tracking
    times_used: int = Field(default=0)
    times_passed: int = Field(default=0)
    times_failed: int = Field(default=0)

    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


# =============================================================================
# REPUTATION HISTORY MODEL
# =============================================================================

class ReputationHistory(SQLModel, table=True):
    """Track reputation changes over time."""

    __tablename__ = "reputation_history"

    id: Optional[int] = Field(default=None, primary_key=True)

    worker_id: int = Field(foreign_key="workers.id", index=True)

    old_reputation: Decimal
    new_reputation: Decimal
    change_amount: Decimal

    reason: str = Field(max_length=100)
    task_id: Optional[int] = Field(default=None, foreign_key="tasks.id")

    created_at: datetime = Field(default_factory=utc_now)
