"""Initial schema migration

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

This migration creates the initial database schema for the Distributed AI Network.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Workers table
    op.create_table(
        'workers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('fingerprint', sa.String(length=512), nullable=True),
        sa.Column('power', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('capabilities', sa.String(length=255), nullable=False, server_default='text'),
        sa.Column('worker_type', sa.String(length=50), nullable=False, server_default='general'),
        sa.Column('balance', sa.Numeric(precision=18, scale=8), nullable=False, server_default='0'),
        sa.Column('pending_balance', sa.Numeric(precision=18, scale=8), nullable=False, server_default='0'),
        sa.Column('total_earned', sa.Numeric(precision=18, scale=8), nullable=False, server_default='0'),
        sa.Column('total_withdrawn', sa.Numeric(precision=18, scale=8), nullable=False, server_default='0'),
        sa.Column('reputation', sa.Numeric(precision=5, scale=2), nullable=False, server_default='1.0'),
        sa.Column('reputation_level', sa.String(length=20), nullable=False, server_default='bronze'),
        sa.Column('tasks_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tasks_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('validations_completed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('validations_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('golden_tasks_passed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('golden_tasks_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='idle'),
        sa.Column('is_banned', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('ban_reason', sa.Text(), nullable=True),
        sa.Column('banned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_task_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
    )
    op.create_index('ix_workers_uuid', 'workers', ['uuid'])
    op.create_index('ix_workers_status', 'workers', ['status'])
    op.create_index('ix_workers_reputation', 'workers', ['reputation'])

    # Tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False, server_default='text'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_golden', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('golden_answer', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('worker_id', sa.Integer(), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('result_hash', sa.String(length=64), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validator_worker_id', sa.Integer(), nullable=True),
        sa.Column('validator_result', sa.Text(), nullable=True),
        sa.Column('validator_result_hash', sa.String(length=64), nullable=True),
        sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('validation_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_validation_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0'),
        sa.Column('reward_worker_a', sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column('reward_worker_b', sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('chunk_id', sa.Integer(), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id']),
        sa.ForeignKeyConstraint(['validator_worker_id'], ['workers.id'])
    )
    op.create_index('ix_tasks_uuid', 'tasks', ['uuid'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])
    op.create_index('ix_tasks_job_id', 'tasks', ['job_id'])

    # Transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('worker_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('balance_before', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('extra_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'])
    )
    op.create_index('ix_transactions_uuid', 'transactions', ['uuid'])
    op.create_index('ix_transactions_worker_id', 'transactions', ['worker_id'])

    # Withdrawal requests table
    op.create_table(
        'withdrawal_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('worker_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column('wallet_address', sa.String(length=255), nullable=True),
        sa.Column('payment_method', sa.String(length=50), nullable=False, server_default='internal'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('processed_by', sa.Integer(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('transaction_hash', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id']),
        sa.ForeignKeyConstraint(['processed_by'], ['workers.id'])
    )
    op.create_index('ix_withdrawal_requests_uuid', 'withdrawal_requests', ['uuid'])

    # AI Jobs table (Kafka pipeline)
    op.create_table(
        'ai_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False, server_default='sentiment_analysis'),
        sa.Column('source_file', sa.String(length=255), nullable=True),
        sa.Column('total_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('result_summary', postgresql.JSONB(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index('ix_ai_jobs_job_id', 'ai_jobs', ['job_id'])
    op.create_index('ix_ai_jobs_status', 'ai_jobs', ['status'])

    # AI Results table
    op.create_table(
        'ai_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=False),
        sa.Column('result', postgresql.JSONB(), nullable=False),
        sa.Column('worker_type', sa.String(length=50), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['job_id'], ['ai_jobs.job_id'])
    )
    op.create_index('ix_ai_results_job_id', 'ai_results', ['job_id'])

    # AI Job Events table
    op.create_table(
        'ai_job_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('chunk_id', sa.Integer(), nullable=True),
        sa.Column('extra_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['job_id'], ['ai_jobs.job_id'])
    )
    op.create_index('ix_ai_job_events_job_id', 'ai_job_events', ['job_id'])

    # Audit Log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('actor_type', sa.String(length=50), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('target_type', sa.String(length=50), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])

    # Golden Tasks table
    op.create_table(
        'golden_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('expected_answer', sa.Text(), nullable=False),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_passed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('times_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Reputation History table
    op.create_table(
        'reputation_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('worker_id', sa.Integer(), nullable=False),
        sa.Column('old_reputation', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('new_reputation', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('change_amount', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id']),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'])
    )
    op.create_index('ix_reputation_history_worker_id', 'reputation_history', ['worker_id'])


def downgrade() -> None:
    op.drop_table('reputation_history')
    op.drop_table('golden_tasks')
    op.drop_table('audit_log')
    op.drop_table('ai_job_events')
    op.drop_table('ai_results')
    op.drop_table('ai_jobs')
    op.drop_table('withdrawal_requests')
    op.drop_table('transactions')
    op.drop_table('tasks')
    op.drop_table('workers')
