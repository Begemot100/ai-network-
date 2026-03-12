-- =============================================================================
-- DISTRIBUTED AI NETWORK - Database Schema
-- Production-grade schema with proper indexes and constraints
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =============================================================================
-- NOTE: Using VARCHAR instead of ENUMs for simpler Python compatibility
-- =============================================================================

-- =============================================================================
-- WORKERS TABLE
-- =============================================================================

CREATE TABLE workers (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,

    -- Identity
    name VARCHAR(255) NOT NULL,
    fingerprint VARCHAR(512),  -- Hardware/browser fingerprint for sybil detection

    -- Capabilities
    power INTEGER NOT NULL DEFAULT 1 CHECK (power >= 1 AND power <= 100),
    capabilities VARCHAR(255) DEFAULT 'text',
    worker_type VARCHAR(50) DEFAULT 'general',

    -- Economy
    balance DECIMAL(18, 8) NOT NULL DEFAULT 0.0 CHECK (balance >= 0),
    pending_balance DECIMAL(18, 8) NOT NULL DEFAULT 0.0 CHECK (pending_balance >= 0),
    total_earned DECIMAL(18, 8) NOT NULL DEFAULT 0.0,
    total_withdrawn DECIMAL(18, 8) NOT NULL DEFAULT 0.0,

    -- Reputation
    reputation DECIMAL(10, 6) NOT NULL DEFAULT 1.0,
    reputation_level VARCHAR(50) NOT NULL DEFAULT 'bronze',

    -- Statistics
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,
    validations_completed INTEGER NOT NULL DEFAULT 0,
    validations_failed INTEGER NOT NULL DEFAULT 0,
    golden_tasks_passed INTEGER NOT NULL DEFAULT 0,
    golden_tasks_failed INTEGER NOT NULL DEFAULT 0,

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'idle',
    is_banned BOOLEAN NOT NULL DEFAULT FALSE,
    ban_reason TEXT,
    banned_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_task_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for workers
CREATE INDEX idx_workers_status ON workers(status) WHERE NOT is_banned;
CREATE INDEX idx_workers_reputation ON workers(reputation DESC);
CREATE INDEX idx_workers_capabilities ON workers USING gin(capabilities gin_trgm_ops);
CREATE INDEX idx_workers_last_seen ON workers(last_seen DESC);
CREATE INDEX idx_workers_uuid ON workers(uuid);

-- =============================================================================
-- TASKS TABLE
-- =============================================================================

CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,

    -- Task definition
    prompt TEXT NOT NULL,
    task_type VARCHAR(50) NOT NULL DEFAULT 'text',
    priority INTEGER NOT NULL DEFAULT 0,
    is_golden BOOLEAN NOT NULL DEFAULT FALSE,
    golden_answer TEXT,  -- For honeypot validation

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Worker A (executor)
    worker_id INTEGER REFERENCES workers(id) ON DELETE SET NULL,
    result TEXT,
    result_hash VARCHAR(64),  -- SHA256 of result for integrity
    submitted_at TIMESTAMP WITH TIME ZONE,

    -- Worker B (validator)
    validator_worker_id INTEGER REFERENCES workers(id) ON DELETE SET NULL,
    validator_result TEXT,
    validator_result_hash VARCHAR(64),
    validated_at TIMESTAMP WITH TIME ZONE,

    -- Validation
    validation_attempts INTEGER NOT NULL DEFAULT 0,
    max_validation_attempts INTEGER NOT NULL DEFAULT 3,
    confidence DECIMAL(5, 4) DEFAULT 0.0,

    -- Rewards (calculated at validation time)
    reward_worker_a DECIMAL(18, 8),
    reward_worker_b DECIMAL(18, 8),

    -- Job reference (for Kafka pipeline tasks)
    job_id VARCHAR(36),
    chunk_id INTEGER,

    -- Lease management
    lease_expires_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for tasks
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_pending ON tasks(id) WHERE status = 'pending';
CREATE INDEX idx_tasks_submitted ON tasks(id) WHERE status = 'submitted_A';
CREATE INDEX idx_tasks_worker ON tasks(worker_id) WHERE worker_id IS NOT NULL;
CREATE INDEX idx_tasks_validator ON tasks(validator_worker_id) WHERE validator_worker_id IS NOT NULL;
CREATE INDEX idx_tasks_job ON tasks(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX idx_tasks_lease ON tasks(lease_expires_at) WHERE lease_expires_at IS NOT NULL;

-- =============================================================================
-- TRANSACTIONS TABLE
-- =============================================================================

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,

    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,

    -- Transaction details
    type VARCHAR(50) NOT NULL,
    amount DECIMAL(18, 8) NOT NULL,
    balance_before DECIMAL(18, 8) NOT NULL,
    balance_after DECIMAL(18, 8) NOT NULL,

    -- Reference
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    extra_data JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for transactions
CREATE INDEX idx_transactions_worker ON transactions(worker_id);
CREATE INDEX idx_transactions_type ON transactions(type);
CREATE INDEX idx_transactions_created ON transactions(created_at DESC);
CREATE INDEX idx_transactions_task ON transactions(task_id) WHERE task_id IS NOT NULL;

-- =============================================================================
-- WITHDRAWAL REQUESTS TABLE
-- =============================================================================

CREATE TABLE withdrawal_requests (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,

    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,

    amount DECIMAL(18, 8) NOT NULL CHECK (amount > 0),
    wallet_address VARCHAR(255),
    payment_method VARCHAR(50) DEFAULT 'internal',

    status VARCHAR(50) NOT NULL DEFAULT 'pending',

    -- Admin handling
    processed_by INTEGER REFERENCES workers(id),
    processed_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    transaction_hash VARCHAR(255),  -- For blockchain payments

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for withdrawal_requests
CREATE INDEX idx_withdrawals_worker ON withdrawal_requests(worker_id);
CREATE INDEX idx_withdrawals_status ON withdrawal_requests(status);
CREATE INDEX idx_withdrawals_created ON withdrawal_requests(created_at DESC);

-- =============================================================================
-- JOBS TABLE (Kafka pipeline)
-- =============================================================================

CREATE TABLE ai_jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(36) UNIQUE NOT NULL,

    -- Job definition
    job_type VARCHAR(50) NOT NULL DEFAULT 'sentiment_analysis',
    source_file VARCHAR(255),

    -- Progress
    total_chunks INTEGER NOT NULL DEFAULT 0,
    completed_chunks INTEGER NOT NULL DEFAULT 0,
    failed_chunks INTEGER NOT NULL DEFAULT 0,

    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message TEXT,

    -- Results
    result_summary JSONB,

    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for ai_jobs
CREATE INDEX idx_jobs_status ON ai_jobs(status);
CREATE INDEX idx_jobs_created ON ai_jobs(created_at DESC);

-- =============================================================================
-- JOB RESULTS TABLE
-- =============================================================================

CREATE TABLE ai_results (
    id SERIAL PRIMARY KEY,

    job_id VARCHAR(36) NOT NULL REFERENCES ai_jobs(job_id) ON DELETE CASCADE,
    chunk_id INTEGER NOT NULL,

    -- Result
    result JSONB NOT NULL,
    worker_type VARCHAR(50),
    processing_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(job_id, chunk_id)
);

-- Indexes for ai_results
CREATE INDEX idx_results_job ON ai_results(job_id);

-- =============================================================================
-- JOB EVENTS TABLE (for WebSocket streaming)
-- =============================================================================

CREATE TABLE ai_job_events (
    id SERIAL PRIMARY KEY,

    job_id VARCHAR(36) NOT NULL REFERENCES ai_jobs(job_id) ON DELETE CASCADE,

    event_type VARCHAR(50) NOT NULL,
    chunk_id INTEGER,
    extra_data JSONB DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for ai_job_events
CREATE INDEX idx_events_job ON ai_job_events(job_id);
CREATE INDEX idx_events_job_id ON ai_job_events(job_id, id);

-- =============================================================================
-- AUDIT LOG TABLE
-- =============================================================================

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,

    -- Action
    action VARCHAR(50) NOT NULL,

    -- Actor
    actor_type VARCHAR(50) NOT NULL,  -- 'worker', 'system', 'admin'
    actor_id INTEGER,

    -- Target
    target_type VARCHAR(50),  -- 'worker', 'task', 'job', 'withdrawal'
    target_id INTEGER,

    -- Details
    details JSONB NOT NULL DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for audit_log
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_actor ON audit_log(actor_type, actor_id);
CREATE INDEX idx_audit_target ON audit_log(target_type, target_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);

-- Partitioning support for audit_log (for production)
-- CREATE INDEX idx_audit_created_brin ON audit_log USING BRIN(created_at);

-- =============================================================================
-- GOLDEN TASKS TABLE (honeypots)
-- =============================================================================

CREATE TABLE golden_tasks (
    id SERIAL PRIMARY KEY,

    prompt TEXT NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    expected_answer TEXT NOT NULL,

    -- Usage tracking
    times_used INTEGER NOT NULL DEFAULT 0,
    times_passed INTEGER NOT NULL DEFAULT 0,
    times_failed INTEGER NOT NULL DEFAULT 0,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================================================
-- REPUTATION HISTORY TABLE
-- =============================================================================

CREATE TABLE reputation_history (
    id SERIAL PRIMARY KEY,

    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,

    old_reputation DECIMAL(10, 6) NOT NULL,
    new_reputation DECIMAL(10, 6) NOT NULL,
    change_amount DECIMAL(10, 6) NOT NULL,

    reason VARCHAR(100) NOT NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for reputation_history
CREATE INDEX idx_rep_history_worker ON reputation_history(worker_id);
CREATE INDEX idx_rep_history_created ON reputation_history(created_at DESC);

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

-- Function to update worker reputation level based on reputation score
CREATE OR REPLACE FUNCTION update_reputation_level()
RETURNS TRIGGER AS $$
BEGIN
    NEW.reputation_level := CASE
        WHEN NEW.reputation >= 5.0 THEN 'diamond'
        WHEN NEW.reputation >= 3.0 THEN 'platinum'
        WHEN NEW.reputation >= 2.0 THEN 'gold'
        WHEN NEW.reputation >= 1.5 THEN 'silver'
        ELSE 'bronze'
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for reputation level
CREATE TRIGGER trigger_update_reputation_level
    BEFORE UPDATE OF reputation ON workers
    FOR EACH ROW
    EXECUTE FUNCTION update_reputation_level();

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER trigger_workers_updated_at
    BEFORE UPDATE ON workers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_jobs_updated_at
    BEFORE UPDATE ON ai_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_withdrawals_updated_at
    BEFORE UPDATE ON withdrawal_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- INITIAL DATA
-- =============================================================================

-- Insert some golden tasks for testing
INSERT INTO golden_tasks (prompt, task_type, expected_answer) VALUES
    ('reverse:hello', 'reverse', 'olleh'),
    ('reverse:world', 'reverse', 'dlrow'),
    ('reverse:test123', 'reverse', '321tset'),
    ('What is 2+2?', 'math', '4'),
    ('What is 10*5?', 'math', '50');

-- =============================================================================
-- VIEWS
-- =============================================================================

-- View for worker statistics
CREATE VIEW worker_stats AS
SELECT
    w.id,
    w.name,
    w.reputation,
    w.reputation_level,
    w.balance,
    w.tasks_completed,
    w.tasks_failed,
    w.validations_completed,
    CASE
        WHEN (w.tasks_completed + w.tasks_failed) > 0
        THEN ROUND(w.tasks_completed::DECIMAL / (w.tasks_completed + w.tasks_failed) * 100, 2)
        ELSE 0
    END AS success_rate,
    w.status,
    w.last_seen,
    w.created_at
FROM workers w
WHERE NOT w.is_banned;

-- View for task pipeline stats
CREATE VIEW task_pipeline_stats AS
SELECT
    status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_duration_seconds
FROM tasks
GROUP BY status;

-- View for job progress
CREATE VIEW job_progress AS
SELECT
    j.job_id,
    j.job_type,
    j.status,
    j.total_chunks,
    j.completed_chunks,
    j.failed_chunks,
    CASE
        WHEN j.total_chunks > 0
        THEN ROUND(j.completed_chunks::DECIMAL / j.total_chunks * 100, 2)
        ELSE 0
    END AS progress_percent,
    j.created_at,
    j.completed_at
FROM ai_jobs j;

-- =============================================================================
-- GRANTS (for production, adjust as needed)
-- =============================================================================

-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_app;
