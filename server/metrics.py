"""
Prometheus metrics for Distributed AI Network.

Exposes key metrics for monitoring:
- Worker statistics
- Task throughput
- Validation rates
- Queue depths
- Error rates
"""

import sys
import time
from functools import wraps
from typing import Callable

from prometheus_client import (
    Counter, Gauge, Histogram, Info,
    generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
)
from starlette.requests import Request
from starlette.responses import Response


# =============================================================================
# CUSTOM REGISTRY (avoids reload conflicts)
# =============================================================================

# Reuse existing registry if module was already loaded (handles uvicorn reload)
_MODULE_NAME = __name__
if hasattr(sys.modules.get(_MODULE_NAME, None), 'METRICS_REGISTRY'):
    METRICS_REGISTRY = sys.modules[_MODULE_NAME].METRICS_REGISTRY
else:
    METRICS_REGISTRY = CollectorRegistry(auto_describe=True)


def _get_or_create(metric_class, name, doc, labels=None, **kwargs):
    """Get existing metric or create new one."""
    # Normalize name for lookup (Counter adds _total, etc.)
    base_name = name
    for suffix in ('_total', '_bucket', '_count', '_sum', '_created'):
        base_name = base_name.replace(suffix, '')

    # Check if already in our registry
    for collector in list(METRICS_REGISTRY._names_to_collectors.values()):
        if hasattr(collector, '_name') and collector._name == base_name:
            return collector

    # Try to create, catch duplicate and return existing
    try:
        if labels:
            return metric_class(name, doc, labels, registry=METRICS_REGISTRY, **kwargs)
        else:
            return metric_class(name, doc, registry=METRICS_REGISTRY, **kwargs)
    except ValueError as e:
        if 'Duplicated timeseries' in str(e):
            # Find the existing metric
            for collector in list(METRICS_REGISTRY._names_to_collectors.values()):
                if hasattr(collector, '_name') and collector._name == base_name:
                    return collector
            # If still not found, raise
        raise


# =============================================================================
# SERVICE INFO
# =============================================================================

SERVICE_INFO = _get_or_create(Info, 'ai_network_service', 'Service information')
if hasattr(SERVICE_INFO, 'info'):
    try:
        SERVICE_INFO.info({'version': '1.0.0', 'service': 'ai-network-main-server'})
    except Exception:
        pass  # Already set

# =============================================================================
# WORKER METRICS
# =============================================================================

WORKERS_TOTAL = _get_or_create(Gauge, 'ai_network_workers_total',
    'Total number of registered workers', ['status'])

WORKERS_ACTIVE = _get_or_create(Gauge, 'ai_network_workers_active',
    'Number of active workers (seen in last 5 minutes)')

WORKERS_REPUTATION = _get_or_create(Histogram, 'ai_network_worker_reputation',
    'Distribution of worker reputations',
    buckets=[0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0])

# =============================================================================
# TASK METRICS
# =============================================================================

TASKS_TOTAL = _get_or_create(Counter, 'ai_network_tasks_total',
    'Total number of tasks', ['status', 'task_type'])

TASKS_CREATED = _get_or_create(Counter, 'ai_network_tasks_created_total',
    'Total tasks created', ['task_type'])

TASKS_COMPLETED = _get_or_create(Counter, 'ai_network_tasks_completed_total',
    'Total tasks completed successfully', ['task_type'])

TASKS_REJECTED = _get_or_create(Counter, 'ai_network_tasks_rejected_total',
    'Total tasks rejected during validation', ['task_type', 'reason'])

TASKS_QUEUE_SIZE = _get_or_create(Gauge, 'ai_network_tasks_queue_size',
    'Number of tasks in queue', ['status'])

TASK_PROCESSING_TIME = _get_or_create(Histogram, 'ai_network_task_processing_seconds',
    'Task processing time', ['task_type'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0])

VALIDATION_TIME = _get_or_create(Histogram, 'ai_network_validation_seconds',
    'Time from submission to validation', ['result'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0])

# =============================================================================
# GOLDEN TASK METRICS
# =============================================================================

GOLDEN_TASKS_TOTAL = _get_or_create(Counter, 'ai_network_golden_tasks_total',
    'Total golden tasks processed', ['result'])

GOLDEN_TASK_PASS_RATE = _get_or_create(Gauge, 'ai_network_golden_task_pass_rate',
    'Golden task pass rate (0-1)')

# =============================================================================
# FINANCIAL METRICS
# =============================================================================

TOTAL_BALANCE = _get_or_create(Gauge, 'ai_network_total_balance',
    'Total balance across all workers')

TOTAL_EARNED = _get_or_create(Gauge, 'ai_network_total_earned',
    'Total amount earned by workers')

PENDING_WITHDRAWALS = _get_or_create(Gauge, 'ai_network_pending_withdrawals',
    'Total pending withdrawal amount')

TRANSACTIONS_TOTAL = _get_or_create(Counter, 'ai_network_transactions_total',
    'Total transactions', ['type'])

TRANSACTION_AMOUNT = _get_or_create(Counter, 'ai_network_transaction_amount_total',
    'Total transaction amounts', ['type'])

# =============================================================================
# HTTP REQUEST METRICS
# =============================================================================

HTTP_REQUESTS_TOTAL = _get_or_create(Counter, 'ai_network_http_requests_total',
    'Total HTTP requests', ['method', 'endpoint', 'status'])

HTTP_REQUEST_DURATION = _get_or_create(Histogram, 'ai_network_http_request_duration_seconds',
    'HTTP request duration', ['method', 'endpoint'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])

# =============================================================================
# ERROR METRICS
# =============================================================================

ERRORS_TOTAL = _get_or_create(Counter, 'ai_network_errors_total',
    'Total errors', ['type', 'source'])

# =============================================================================
# DATABASE METRICS
# =============================================================================

DB_POOL_SIZE = _get_or_create(Gauge, 'ai_network_db_pool_size',
    'Database connection pool size')

DB_POOL_CHECKED_OUT = _get_or_create(Gauge, 'ai_network_db_pool_checked_out',
    'Database connections currently checked out')

DB_QUERIES_TOTAL = _get_or_create(Counter, 'ai_network_db_queries_total',
    'Total database queries')

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def update_worker_metrics(session) -> None:
    """Update worker-related metrics from database."""
    from sqlmodel import select, func
    from datetime import datetime, timedelta, timezone

    from .models import Worker

    # Count by status
    for status in ['idle', 'online', 'working', 'offline', 'banned']:
        count = session.exec(
            select(func.count(Worker.id))
            .where(Worker.status == status)
        ).one()
        WORKERS_TOTAL.labels(status=status).set(count)

    # Active workers
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    active = session.exec(
        select(func.count(Worker.id))
        .where(Worker.last_seen >= threshold)
    ).one()
    WORKERS_ACTIVE.set(active)

    # Reputation distribution
    workers = session.exec(select(Worker.reputation)).all()
    for rep in workers:
        WORKERS_REPUTATION.observe(float(rep))


def update_task_metrics(session) -> None:
    """Update task-related metrics from database."""
    from sqlmodel import select, func

    from .models import Task

    # Queue sizes
    for status in ['pending', 'assigned', 'submitted_A', 'validating']:
        count = session.exec(
            select(func.count(Task.id))
            .where(Task.status == status)
        ).one()
        TASKS_QUEUE_SIZE.labels(status=status).set(count)


def update_financial_metrics(session) -> None:
    """Update financial metrics from database."""
    from sqlmodel import select, func
    from decimal import Decimal

    from .models import Worker, WithdrawalRequest

    # Total balance
    total_balance = session.exec(
        select(func.sum(Worker.balance))
    ).one() or Decimal("0")
    TOTAL_BALANCE.set(float(total_balance))

    # Total earned
    total_earned = session.exec(
        select(func.sum(Worker.total_earned))
    ).one() or Decimal("0")
    TOTAL_EARNED.set(float(total_earned))

    # Pending withdrawals
    pending = session.exec(
        select(func.sum(WithdrawalRequest.amount))
        .where(WithdrawalRequest.status == "pending")
    ).one() or Decimal("0")
    PENDING_WITHDRAWALS.set(float(pending))


def update_golden_task_metrics(session) -> None:
    """Update golden task metrics."""
    from sqlmodel import select, func

    from .models import Worker

    passed = session.exec(
        select(func.sum(Worker.golden_tasks_passed))
    ).one() or 0

    failed = session.exec(
        select(func.sum(Worker.golden_tasks_failed))
    ).one() or 0

    total = passed + failed
    if total > 0:
        GOLDEN_TASK_PASS_RATE.set(passed / total)


def update_all_metrics(session) -> None:
    """Update all metrics from database."""
    update_worker_metrics(session)
    update_task_metrics(session)
    update_financial_metrics(session)
    update_golden_task_metrics(session)


# =============================================================================
# METRIC DECORATORS
# =============================================================================

def track_request(func: Callable) -> Callable:
    """Decorator to track HTTP request metrics."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        start = time.time()
        try:
            response = await func(request, *args, **kwargs)
            status = response.status_code
        except Exception as e:
            status = 500
            raise
        finally:
            duration = time.time() - start
            endpoint = request.url.path
            method = request.method

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status=str(status)
            ).inc()

            HTTP_REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

        return response
    return wrapper


# =============================================================================
# PROMETHEUS ENDPOINT
# =============================================================================

async def metrics_endpoint(request: Request) -> Response:
    """Prometheus metrics endpoint."""
    # Update metrics before returning
    from .db import get_db_session, get_db_stats

    try:
        with get_db_session() as session:
            update_all_metrics(session)

        # Update DB pool stats
        stats = get_db_stats()
        DB_POOL_SIZE.set(stats.get('pool_size', 0))
        DB_POOL_CHECKED_OUT.set(stats.get('checked_out', 0))
    except Exception:
        pass  # Don't fail metrics endpoint if DB is unavailable

    return Response(
        content=generate_latest(METRICS_REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )


# =============================================================================
# HELPER FUNCTIONS FOR TRACKING
# =============================================================================

def track_task_created(task_type: str) -> None:
    """Track task creation."""
    TASKS_CREATED.labels(task_type=task_type).inc()


def track_task_completed(task_type: str, processing_time: float) -> None:
    """Track task completion."""
    TASKS_COMPLETED.labels(task_type=task_type).inc()
    TASK_PROCESSING_TIME.labels(task_type=task_type).observe(processing_time)


def track_task_rejected(task_type: str, reason: str) -> None:
    """Track task rejection."""
    TASKS_REJECTED.labels(task_type=task_type, reason=reason).inc()


def track_validation(result: str, validation_time: float) -> None:
    """Track validation completion."""
    VALIDATION_TIME.labels(result=result).observe(validation_time)


def track_golden_task(passed: bool) -> None:
    """Track golden task result."""
    GOLDEN_TASKS_TOTAL.labels(result="passed" if passed else "failed").inc()


def track_transaction(tx_type: str, amount: float) -> None:
    """Track financial transaction."""
    TRANSACTIONS_TOTAL.labels(type=tx_type).inc()
    TRANSACTION_AMOUNT.labels(type=tx_type).inc(amount)


def track_error(error_type: str, source: str) -> None:
    """Track error occurrence."""
    ERRORS_TOTAL.labels(type=error_type, source=source).inc()
