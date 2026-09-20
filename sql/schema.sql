-- LogFlow Schema: log_events table
-- Stores structured application log records from the processing pipeline.

CREATE TABLE IF NOT EXISTS log_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    timestamp       TIMESTAMP NOT NULL,
    log_level       VARCHAR(10) NOT NULL,
    event_type      VARCHAR(30) NOT NULL,
    service         VARCHAR(30),
    endpoint        VARCHAR(100),
    method          VARCHAR(10),
    status          INTEGER,
    response_time_ms INTEGER,
    user_id         VARCHAR(20),
    message         TEXT,
    record_hash     VARCHAR(64) NOT NULL UNIQUE,

    -- Valid log levels only
    CONSTRAINT chk_log_level CHECK (log_level IN ('DEBUG', 'INFO', 'WARN', 'ERROR')),

    -- Response time must be non-negative when present
    CONSTRAINT chk_response_time CHECK (response_time_ms IS NULL OR response_time_ms >= 0),

    -- HTTP status in sensible range when present
    CONSTRAINT chk_status CHECK (status IS NULL OR (status >= 100 AND status <= 599))
);

-- Indexes for Part 5 analytics and Part 6 anomaly detection

-- Timestamp index: daily/hourly activity, trend analysis, time-range queries
CREATE INDEX IF NOT EXISTS idx_log_events_timestamp ON log_events (timestamp);

-- Log level index: error analysis, filtering by severity
CREATE INDEX IF NOT EXISTS idx_log_events_log_level ON log_events (log_level);

-- Event type index: event distribution analysis
CREATE INDEX IF NOT EXISTS idx_log_events_event_type ON log_events (event_type);

-- Service index: per-service analysis
CREATE INDEX IF NOT EXISTS idx_log_events_service ON log_events (service);

-- Endpoint index: API usage analysis, slow endpoint detection
CREATE INDEX IF NOT EXISTS idx_log_events_endpoint ON log_events (endpoint);

-- User index: user activity analysis
CREATE INDEX IF NOT EXISTS idx_log_events_user_id ON log_events (user_id);

-- Composite index: common query pattern for error analysis by service and time
CREATE INDEX IF NOT EXISTS idx_log_events_level_service_ts
    ON log_events (log_level, service, timestamp);
