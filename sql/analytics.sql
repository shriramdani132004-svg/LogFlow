-- LogFlow SQL Analytics
-- Queries for Part 5: operational statistics from the log_events table.

-- ============================================================
-- 1. Overall Summary
-- ============================================================
SELECT
    COUNT(*)                              AS total_records,
    MIN(timestamp)                        AS earliest_timestamp,
    MAX(timestamp)                        AS latest_timestamp
FROM log_events;

-- ============================================================
-- 2. Log Level Distribution
-- ============================================================
SELECT
    log_level,
    COUNT(*)                              AS event_count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM log_events
GROUP BY log_level
ORDER BY event_count DESC;

-- ============================================================
-- 3. Event Type Distribution
-- ============================================================
SELECT
    event_type,
    COUNT(*)                              AS event_count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM log_events
GROUP BY event_type
ORDER BY event_count DESC;

-- ============================================================
-- 4. Service Distribution
-- ============================================================
SELECT
    service,
    COUNT(*)                              AS event_count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM log_events
GROUP BY service
ORDER BY event_count DESC;

-- ============================================================
-- 5. HTTP Status Code Distribution
-- ============================================================
SELECT
    status,
    COUNT(*)                              AS event_count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM log_events
GROUP BY status
ORDER BY status;

-- ============================================================
-- 6. HTTP Status Class Distribution (2xx, 3xx, 4xx, 5xx)
-- ============================================================
SELECT
    CASE
        WHEN status >= 200 AND status < 300 THEN '2xx'
        WHEN status >= 300 AND status < 400 THEN '3xx'
        WHEN status >= 400 AND status < 500 THEN '4xx'
        WHEN status >= 500 AND status < 600 THEN '5xx'
        ELSE 'other'
    END                                   AS status_class,
    COUNT(*)                              AS event_count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM log_events
GROUP BY status_class
ORDER BY status_class;

-- ============================================================
-- 7. Error Summary
-- ============================================================
SELECT
    COUNT(*) FILTER (WHERE log_level = 'ERROR')   AS total_errors,
    COUNT(*) FILTER (WHERE log_level = 'WARN')    AS total_warnings,
    COUNT(*) FILTER (WHERE event_type = 'AUTH_FAILURE') AS auth_failures,
    COUNT(*) FILTER (WHERE event_type = 'DATABASE_ERROR') AS database_errors
FROM log_events;

-- ============================================================
-- 8. Response Time Summary
-- ============================================================
SELECT
    ROUND(AVG(response_time_ms)::numeric, 2)  AS avg_response_time_ms,
    MIN(response_time_ms)                      AS min_response_time_ms,
    MAX(response_time_ms)                      AS max_response_time_ms,
    COUNT(response_time_ms)                    AS samples
FROM log_events
WHERE response_time_ms IS NOT NULL;

-- ============================================================
-- 9. Slowest Endpoints (top 10)
-- ============================================================
SELECT
    endpoint,
    COUNT(*)                               AS request_count,
    ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms,
    MAX(response_time_ms)                  AS max_response_time_ms
FROM log_events
WHERE endpoint IS NOT NULL
  AND response_time_ms IS NOT NULL
GROUP BY endpoint
ORDER BY avg_response_time_ms DESC
LIMIT 10;

-- ============================================================
-- 10. Most-Used Endpoints (top 10)
-- ============================================================
SELECT
    endpoint,
    COUNT(*)                               AS request_count,
    ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms
FROM log_events
WHERE endpoint IS NOT NULL
GROUP BY endpoint
ORDER BY request_count DESC
LIMIT 10;

-- ============================================================
-- 11. Service Performance
-- ============================================================
SELECT
    service,
    COUNT(*)                               AS total_count,
    COUNT(*) FILTER (WHERE log_level = 'ERROR') AS error_count,
    ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms,
    MAX(response_time_ms)                  AS max_response_time_ms
FROM log_events
WHERE service IS NOT NULL
GROUP BY service
ORDER BY error_count DESC, avg_response_time_ms DESC;

-- ============================================================
-- 12. Hourly Traffic
-- ============================================================
SELECT
    DATE_TRUNC('hour', timestamp)          AS hour,
    COUNT(*)                               AS event_count
FROM log_events
GROUP BY hour
ORDER BY hour;

-- ============================================================
-- 13. User Activity Summary (users with user_id)
-- ============================================================
SELECT
    user_id,
    COUNT(*)                               AS event_count,
    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
FROM log_events
WHERE user_id IS NOT NULL
GROUP BY user_id
ORDER BY event_count DESC;
