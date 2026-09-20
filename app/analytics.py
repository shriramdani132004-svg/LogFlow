import json
import logging
from datetime import datetime, date
from decimal import Decimal

from app.database import close_connection, get_connection

logger = logging.getLogger(__name__)

_NA = "N/A"


def _fmt(value, width=None):
    if value is None:
        if width is not None:
            return _NA.ljust(width)
        return _NA
    if width is not None:
        return f"{value:<{width}}"
    return str(value)


def _fmt_pct(value):
    if value is None:
        return "N/A"
    return f"{value}"


def _fmt_ms(value):
    if value is None:
        return "N/A"
    return f"{value}"


def _fetch_one(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def _fetch_all(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def _safe_float(val):
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def _row_to_dict(columns, row):
    return {col: _safe_float(row[i]) for i, col in enumerate(columns)}


def _rows_to_dicts(columns, rows):
    return [_row_to_dict(columns, row) for row in rows]


def table_exists(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'log_events'
            )
        """)
        return cur.fetchone()[0]


def get_overall_summary():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return {"total_records": 0, "earliest_timestamp": None, "latest_timestamp": None}
        row = _fetch_one(conn, """
            SELECT
                COUNT(*)        AS total_records,
                MIN(timestamp)  AS earliest_timestamp,
                MAX(timestamp)  AS latest_timestamp
            FROM log_events
        """)
        return _row_to_dict(
            ["total_records", "earliest_timestamp", "latest_timestamp"], row
        )
    except Exception as e:
        logger.error("Overall summary failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_log_level_distribution():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                log_level,
                COUNT(*) AS event_count,
                ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
            FROM log_events
            GROUP BY log_level
            ORDER BY event_count DESC
        """)
        return _rows_to_dicts(["log_level", "event_count", "pct"], rows)
    except Exception as e:
        logger.error("Log level distribution failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_event_type_distribution():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                event_type,
                COUNT(*) AS event_count,
                ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
            FROM log_events
            GROUP BY event_type
            ORDER BY event_count DESC
        """)
        return _rows_to_dicts(["event_type", "event_count", "pct"], rows)
    except Exception as e:
        logger.error("Event type distribution failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_service_distribution():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                service,
                COUNT(*) AS event_count,
                ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
            FROM log_events
            GROUP BY service
            ORDER BY event_count DESC
        """)
        return _rows_to_dicts(["service", "event_count", "pct"], rows)
    except Exception as e:
        logger.error("Service distribution failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_status_distribution():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                status,
                COUNT(*) AS event_count,
                ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
            FROM log_events
            GROUP BY status
            ORDER BY status
        """)
        return _rows_to_dicts(["status", "event_count", "pct"], rows)
    except Exception as e:
        logger.error("Status distribution failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_status_class_distribution():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                CASE
                    WHEN status >= 200 AND status < 300 THEN '2xx'
                    WHEN status >= 300 AND status < 400 THEN '3xx'
                    WHEN status >= 400 AND status < 500 THEN '4xx'
                    WHEN status >= 500 AND status < 600 THEN '5xx'
                    ELSE 'other'
                END AS status_class,
                COUNT(*) AS event_count,
                ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
            FROM log_events
            GROUP BY status_class
            ORDER BY status_class
        """)
        return _rows_to_dicts(["status_class", "event_count", "pct"], rows)
    except Exception as e:
        logger.error("Status class distribution failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_error_summary():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return {"total_errors": 0, "total_warnings": 0, "auth_failures": 0, "database_errors": 0}
        row = _fetch_one(conn, """
            SELECT
                COUNT(*) FILTER (WHERE log_level = 'ERROR')              AS total_errors,
                COUNT(*) FILTER (WHERE log_level = 'WARN')               AS total_warnings,
                COUNT(*) FILTER (WHERE event_type = 'AUTH_FAILURE')      AS auth_failures,
                COUNT(*) FILTER (WHERE event_type = 'DATABASE_ERROR')    AS database_errors
            FROM log_events
        """)
        return _row_to_dict(
            ["total_errors", "total_warnings", "auth_failures", "database_errors"], row
        )
    except Exception as e:
        logger.error("Error summary failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_response_time_summary():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return {"avg_response_time_ms": None, "min_response_time_ms": None, "max_response_time_ms": None, "samples": 0}
        row = _fetch_one(conn, """
            SELECT
                ROUND(AVG(response_time_ms)::numeric, 2)  AS avg_response_time_ms,
                MIN(response_time_ms)                      AS min_response_time_ms,
                MAX(response_time_ms)                      AS max_response_time_ms,
                COUNT(response_time_ms)                    AS samples
            FROM log_events
            WHERE response_time_ms IS NOT NULL
        """)
        return _row_to_dict(
            ["avg_response_time_ms", "min_response_time_ms", "max_response_time_ms", "samples"], row
        )
    except Exception as e:
        logger.error("Response time summary failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_slowest_endpoints(limit=10):
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, f"""
            SELECT
                endpoint,
                COUNT(*)                                AS request_count,
                ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms,
                MAX(response_time_ms)                   AS max_response_time_ms
            FROM log_events
            WHERE endpoint IS NOT NULL
              AND response_time_ms IS NOT NULL
            GROUP BY endpoint
            ORDER BY avg_response_time_ms DESC
            LIMIT {int(limit)}
        """)
        return _rows_to_dicts(
            ["endpoint", "request_count", "avg_response_time_ms", "max_response_time_ms"], rows
        )
    except Exception as e:
        logger.error("Slowest endpoints failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_most_used_endpoints(limit=10):
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, f"""
            SELECT
                endpoint,
                COUNT(*)                                AS request_count,
                ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms
            FROM log_events
            WHERE endpoint IS NOT NULL
            GROUP BY endpoint
            ORDER BY request_count DESC
            LIMIT {int(limit)}
        """)
        return _rows_to_dicts(
            ["endpoint", "request_count", "avg_response_time_ms"], rows
        )
    except Exception as e:
        logger.error("Most used endpoints failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_service_performance():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                service,
                COUNT(*)                                                AS total_count,
                COUNT(*) FILTER (WHERE log_level = 'ERROR')             AS error_count,
                ROUND(AVG(response_time_ms)::numeric, 2)                AS avg_response_time_ms,
                MAX(response_time_ms)                                   AS max_response_time_ms
            FROM log_events
            WHERE service IS NOT NULL
            GROUP BY service
            ORDER BY error_count DESC, avg_response_time_ms DESC
        """)
        return _rows_to_dicts(
            ["service", "total_count", "error_count", "avg_response_time_ms", "max_response_time_ms"],
            rows,
        )
    except Exception as e:
        logger.error("Service performance failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_hourly_traffic():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                DATE_TRUNC('hour', timestamp)   AS hour,
                COUNT(*)                        AS event_count
            FROM log_events
            GROUP BY hour
            ORDER BY hour
        """)
        return _rows_to_dicts(["hour", "event_count"], rows)
    except Exception as e:
        logger.error("Hourly traffic failed: %s", e)
        raise
    finally:
        close_connection(conn)


def get_user_activity_summary():
    conn = None
    try:
        conn = get_connection()
        if not table_exists(conn):
            return []
        rows = _fetch_all(conn, """
            SELECT
                user_id,
                COUNT(*) AS event_count,
                ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) AS pct
            FROM log_events
            WHERE user_id IS NOT NULL
            GROUP BY user_id
            ORDER BY event_count DESC
        """)
        return _rows_to_dicts(["user_id", "event_count", "pct"], rows)
    except Exception as e:
        logger.error("User activity summary failed: %s", e)
        raise
    finally:
        close_connection(conn)


def run_all_analytics():
    return {
        "overall_summary": get_overall_summary(),
        "log_level_distribution": get_log_level_distribution(),
        "event_type_distribution": get_event_type_distribution(),
        "service_distribution": get_service_distribution(),
        "status_distribution": get_status_distribution(),
        "status_class_distribution": get_status_class_distribution(),
        "error_summary": get_error_summary(),
        "response_time_summary": get_response_time_summary(),
        "slowest_endpoints": get_slowest_endpoints(),
        "most_used_endpoints": get_most_used_endpoints(),
        "service_performance": get_service_performance(),
        "hourly_traffic": get_hourly_traffic(),
        "user_activity_summary": get_user_activity_summary(),
    }


def _json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def save_report(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_json_serializer)


def print_report(data):
    s = data["overall_summary"]
    print("## Analytics Summary")
    print()
    print(f"  Total records       : {_fmt(s['total_records'])}")
    print(f"  Earliest timestamp  : {_fmt(s['earliest_timestamp'])}")
    print(f"  Latest timestamp    : {_fmt(s['latest_timestamp'])}")

    print()
    print("## Log Levels")
    for row in data["log_level_distribution"]:
        print(f"  {_fmt(row['log_level'], 8)}: {_fmt(row['event_count'])}  ({_fmt_pct(row['pct'])}%)")

    print()
    print("## Event Types")
    for row in data["event_type_distribution"]:
        print(f"  {_fmt(row['event_type'], 25)}: {_fmt(row['event_count'])}  ({_fmt_pct(row['pct'])}%)")

    print()
    print("## Service Distribution")
    for row in data["service_distribution"]:
        print(f"  {_fmt(row['service'], 20)}: {_fmt(row['event_count'])}  ({_fmt_pct(row['pct'])}%)")

    print()
    print("## HTTP Status Codes")
    for row in data["status_distribution"]:
        print(f"  {_fmt(row['status'], 8)}: {_fmt(row['event_count'])}  ({_fmt_pct(row['pct'])}%)")

    print()
    print("## Status Class Distribution")
    for row in data["status_class_distribution"]:
        print(f"  {_fmt(row['status_class'], 8)}: {_fmt(row['event_count'])}  ({_fmt_pct(row['pct'])}%)")

    print()
    print("## Error Summary")
    es = data["error_summary"]
    print(f"  Total errors        : {_fmt(es['total_errors'])}")
    print(f"  Total warnings      : {_fmt(es['total_warnings'])}")
    print(f"  Auth failures       : {_fmt(es['auth_failures'])}")
    print(f"  Database errors     : {_fmt(es['database_errors'])}")

    print()
    print("## Response Time")
    rt = data["response_time_summary"]
    print(f"  Average : {_fmt_ms(rt['avg_response_time_ms'])} ms")
    print(f"  Minimum : {_fmt_ms(rt['min_response_time_ms'])} ms")
    print(f"  Maximum : {_fmt_ms(rt['max_response_time_ms'])} ms")
    print(f"  Samples : {_fmt(rt['samples'])}")

    print()
    print("## Slowest Endpoints")
    for row in data["slowest_endpoints"]:
        print(f"  {_fmt(row['endpoint'], 35)} avg={_fmt_ms(row['avg_response_time_ms'])} ms  max={_fmt_ms(row['max_response_time_ms'])} ms  ({_fmt(row['request_count'])} reqs)")

    print()
    print("## Most-Used Endpoints")
    for row in data["most_used_endpoints"]:
        print(f"  {_fmt(row['endpoint'], 35)} {_fmt(row['request_count'])} reqs  avg={_fmt_ms(row['avg_response_time_ms'])} ms")

    print()
    print("## Service Performance")
    for row in data["service_performance"]:
        print(f"  {_fmt(row['service'], 20)} total={_fmt(row['total_count'])}  errors={_fmt(row['error_count'])}  avg={_fmt_ms(row['avg_response_time_ms'])} ms  max={_fmt_ms(row['max_response_time_ms'])} ms")

    print()
    print("## Hourly Traffic")
    for row in data["hourly_traffic"]:
        print(f"  {_fmt(row['hour'])}  : {_fmt(row['event_count'])} events")

    print()
    print("## User Activity")
    for row in data["user_activity_summary"]:
        print(f"  {_fmt(row['user_id'], 15)} : {_fmt(row['event_count'])} events  ({_fmt_pct(row['pct'])}%)")
