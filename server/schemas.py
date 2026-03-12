"""
Pydantic schemas for request/response validation.
Production-grade schemas with proper validation and documentation.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any
from pydantic import BaseModel, Field, validator


# =============================================================================
# WORKER SCHEMAS
# =============================================================================

class WorkerRegister(BaseModel):
    """Schema for worker registration request."""

    name: str = Field(..., min_length=1, max_length=255, description="Worker display name")
    power: int = Field(default=1, ge=1, le=100, description="Compute power level (1-100)")
    capabilities: str = Field(default="text", max_length=255, description="Comma-separated capabilities")
    fingerprint: Optional[str] = Field(default=None, max_length=512, description="Hardware fingerprint")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Worker-1",
                "power": 10,
                "capabilities": "text,reverse,math",
            }
        }


class WorkerResponse(BaseModel):
    """Schema for worker information response."""

    id: int
    uuid: str
    name: str
    power: int
    capabilities: str
    balance: Decimal
    pending_balance: Decimal
    reputation: Decimal
    reputation_level: str
    tasks_completed: int
    tasks_failed: int
    validations_completed: int
    success_rate: float
    status: str
    is_banned: bool
    last_seen: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class WorkerListResponse(BaseModel):
    """Schema for paginated worker list."""

    workers: List[WorkerResponse]
    total: int
    page: int
    page_size: int


class WorkerStatsResponse(BaseModel):
    """Schema for worker statistics."""

    total_workers: int
    active_workers: int
    working_workers: int
    banned_workers: int
    total_balance: Decimal
    avg_reputation: float


# =============================================================================
# TASK SCHEMAS
# =============================================================================

class TaskCreate(BaseModel):
    """Schema for task creation request."""

    prompt: str = Field(..., min_length=1, description="Task prompt/input")
    task_type: str = Field(default="text", description="Task type for reward calculation")
    priority: int = Field(default=0, ge=0, le=100, description="Task priority (higher = more urgent)")

    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "reverse:hello world",
                "task_type": "reverse",
                "priority": 0,
            }
        }


class TaskResult(BaseModel):
    """Schema for task result submission."""

    task_id: int = Field(..., description="Task ID")
    worker_id: int = Field(..., description="Worker ID submitting the result")
    result: str = Field(..., description="Computed result")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 1,
                "worker_id": 1,
                "result": "dlrow olleh",
            }
        }


class TaskAssignment(BaseModel):
    """Schema for task assignment response."""

    task_id: int
    prompt: str
    task_type: str
    mode: str = Field(description="'work' for execution, 'validate' for validation")
    is_golden: bool = False
    lease_expires_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 1,
                "prompt": "reverse:hello",
                "task_type": "reverse",
                "mode": "work",
                "is_golden": False,
            }
        }


class TaskResponse(BaseModel):
    """Schema for task details response."""

    id: int
    uuid: str
    prompt: str
    task_type: str
    status: str
    priority: int
    worker_id: Optional[int]
    validator_worker_id: Optional[int]
    result: Optional[str]
    validator_result: Optional[str]
    confidence: Decimal
    reward_worker_a: Optional[Decimal]
    reward_worker_b: Optional[Decimal]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    """Schema for paginated task list."""

    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class TaskStatsResponse(BaseModel):
    """Schema for task statistics."""

    total_tasks: int
    pending_tasks: int
    assigned_tasks: int
    validating_tasks: int
    completed_tasks: int
    rejected_tasks: int


# =============================================================================
# TRANSACTION SCHEMAS
# =============================================================================

class TransactionResponse(BaseModel):
    """Schema for transaction response."""

    id: int
    uuid: str
    type: str
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    description: str
    task_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """Schema for transaction list."""

    transactions: List[TransactionResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# WITHDRAWAL SCHEMAS
# =============================================================================

class WithdrawalRequest(BaseModel):
    """Schema for withdrawal request."""

    worker_id: int = Field(..., description="Worker requesting withdrawal")
    amount: Decimal = Field(..., gt=0, description="Amount to withdraw")
    wallet_address: Optional[str] = Field(default=None, max_length=255, description="Payment address")
    payment_method: str = Field(default="internal", max_length=50, description="Payment method")

    class Config:
        json_schema_extra = {
            "example": {
                "worker_id": 1,
                "amount": "10.00",
                "payment_method": "internal",
            }
        }


class WithdrawalResponse(BaseModel):
    """Schema for withdrawal response."""

    id: int
    uuid: str
    worker_id: int
    amount: Decimal
    status: str
    wallet_address: Optional[str]
    payment_method: str
    rejection_reason: Optional[str]
    transaction_hash: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True


class WithdrawalListResponse(BaseModel):
    """Schema for withdrawal list."""

    withdrawals: List[WithdrawalResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# ADMIN SCHEMAS
# =============================================================================

class BanWorkerRequest(BaseModel):
    """Schema for banning a worker."""

    worker_id: int = Field(..., description="Worker to ban")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for ban")


class UnbanWorkerRequest(BaseModel):
    """Schema for unbanning a worker."""

    worker_id: int = Field(..., description="Worker to unban")


class ProcessWithdrawalRequest(BaseModel):
    """Schema for processing withdrawal."""

    withdrawal_id: int = Field(..., description="Withdrawal request ID")
    action: str = Field(..., description="'approve' or 'reject'")
    reason: Optional[str] = Field(default=None, description="Reason (required for rejection)")
    transaction_hash: Optional[str] = Field(default=None, description="Blockchain tx hash (for crypto)")


# =============================================================================
# GENERIC RESPONSE SCHEMAS
# =============================================================================

class SuccessResponse(BaseModel):
    """Generic success response."""

    status: str = "ok"
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Generic error response."""

    status: str = "error"
    detail: str
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: bool
    redis: bool
    kafka: bool
    version: str
    uptime_seconds: float


# =============================================================================
# WEBSOCKET SCHEMAS
# =============================================================================

class WSMessage(BaseModel):
    """WebSocket message schema."""

    type: str
    data: Any


class WSWorkerUpdate(BaseModel):
    """WebSocket worker update message."""

    type: str = "worker_update"
    worker_id: int
    status: str
    task_id: Optional[int] = None


class WSTaskUpdate(BaseModel):
    """WebSocket task update message."""

    type: str = "task_update"
    task_id: int
    status: str
    worker_id: Optional[int] = None
    validator_worker_id: Optional[int] = None


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

class ValidationResult(BaseModel):
    """Internal schema for validation results."""

    is_match: bool
    result_a: str
    result_b: str
    reward_a: Decimal
    reward_b: Decimal
    reputation_change_a: Decimal
    reputation_change_b: Decimal
    is_golden_task: bool = False
    golden_passed: Optional[bool] = None
