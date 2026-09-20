import csv
import hashlib
import logging
import os
import re
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values

from app.config import (
    CLEANED_OUTPUT,
    DB_BATCH_SIZE,
    OUTPUT_DIR,
    SQL_DIR,
)
from app.database import close_connection, execute_sql_file, get_connection

logger = logging.getLogger(__name__)

SCHEMA_FILE = os.path.join(SQL_DIR, "schema.sql")

REQUIRED_CSV_COLUMNS = [
    "timestamp", "log_level", "event_type", "service",
    "endpoint", "method", "status", "response_time_ms",
    "user_id", "message",
]

HASH_COLUMNS = [
    "timestamp", "log_level", "event_type", "service",
    "endpoint", "method", "status", "response_time_ms",
    "user_id", "message",
]

COMMA_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{1,6}$")
DOT_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6}$")
BASIC_TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def parse_timestamp(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        raise ValueError(f"Cannot parse timestamp from {type(value).__name__}: {value}")

    value = value.strip()
    if not value:
        return None

    if COMMA_TS_PATTERN.match(value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")

    if DOT_TS_PATTERN.match(value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")

    if BASIC_TS_PATTERN.match(value):
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")

    raise ValueError(f"Invalid timestamp format: {value}")


def normalize_timestamp_for_hash(ts):
    if ts is None:
        return ""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond:06d}"
    s = str(ts).strip()
    try:
        dt = parse_timestamp(s)
        if dt is not None:
            return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond:06d}"
    except ValueError:
        pass
    return s.lower()


def compute_record_hash(row):
    parts = []
    for col in HASH_COLUMNS:
        val = row.get(col)
        if val is None:
            parts.append("")
        elif col == "timestamp":
            parts.append(normalize_timestamp_for_hash(val))
        else:
            parts.append(str(val).strip().lower())
    fingerprint = "|".join(parts)
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def validate_csv_columns(csv_path):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)

    if header is None:
        raise ValueError("CSV file is empty")

    header = [h.strip() for h in header]
    missing = [col for col in REQUIRED_CSV_COLUMNS if col not in header]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return header


def convert_csv_value(val, col):
    if val is None or val == "" or val in ("NaN", "None", "null", "NaT", "nan"):
        return None

    if col == "timestamp":
        return val.strip()

    if col == "status":
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    if col == "response_time_ms":
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    return str(val).strip()


def prepare_rows(csv_path):
    validate_csv_columns(csv_path)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            converted = {}
            for col in REQUIRED_CSV_COLUMNS:
                converted[col] = convert_csv_value(row.get(col), col)

            ts_str = converted.get("timestamp")
            if ts_str is None:
                raise ValueError(f"Row {line_num}: missing required timestamp")
            try:
                converted["timestamp"] = parse_timestamp(ts_str)
            except ValueError as e:
                raise ValueError(f"Row {line_num}: {e}")

            converted["record_hash"] = compute_record_hash(converted)
            rows.append(converted)

    return rows


def init_schema():
    conn = None
    try:
        conn = get_connection()
        execute_sql_file(conn, SCHEMA_FILE)
        print("Schema initialized successfully")
    except Exception as e:
        logger.error("Schema initialization failed: %s", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        close_connection(conn)


def load_csv_to_db(csv_path=None):
    if csv_path is None:
        csv_path = CLEANED_OUTPUT

    rows = prepare_rows(csv_path)
    total_input = len(rows)

    if total_input == 0:
        return {
            "input_records": 0,
            "inserted_records": 0,
            "duplicate_records": 0,
            "failed_records": 0,
            "database_total_rows": 0,
        }

    conn = None
    try:
        conn = get_connection()
        conn.autocommit = False

        inserted = 0

        with conn.cursor() as cur:
            for i in range(0, total_input, DB_BATCH_SIZE):
                batch = rows[i:i + DB_BATCH_SIZE]
                batch_values = [
                    (
                        r["timestamp"], r["log_level"], r["event_type"],
                        r["service"], r["endpoint"], r["method"],
                        r["status"], r["response_time_ms"],
                        r["user_id"], r["message"], r["record_hash"],
                    )
                    for r in batch
                ]

                execute_values(
                    cur,
                    """
                    INSERT INTO log_events (
                        timestamp, log_level, event_type,
                        service, endpoint, method,
                        status, response_time_ms,
                        user_id, message, record_hash
                    ) VALUES %s
                    ON CONFLICT (record_hash) DO NOTHING
                    """,
                    batch_values,
                    page_size=DB_BATCH_SIZE,
                )
                inserted += cur.rowcount

            conn.commit()

        duplicates = total_input - inserted

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM log_events")
            total_rows = cur.fetchone()[0]

        stats = {
            "input_records": total_input,
            "inserted_records": inserted,
            "duplicate_records": duplicates,
            "failed_records": 0,
            "database_total_rows": total_rows,
        }

        return stats

    except Exception as e:
        logger.error("Database load failed: %s", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        close_connection(conn)


def verify_database():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'log_events'
                )
            """)
            table_exists = cur.fetchone()[0]

            if not table_exists:
                return {"table_exists": False}

            cur.execute("SELECT COUNT(*) FROM log_events")
            total_rows = cur.fetchone()[0]

            cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM log_events")
            min_ts, max_ts = cur.fetchone()

            cur.execute("""
                SELECT log_level, COUNT(*)
                FROM log_events
                GROUP BY log_level
                ORDER BY log_level
            """)
            level_counts = dict(cur.fetchall())

        return {
            "table_exists": True,
            "total_rows": total_rows,
            "min_timestamp": min_ts,
            "max_timestamp": max_ts,
            "level_counts": level_counts,
        }

    except Exception as e:
        logger.error("Database verification failed: %s", e)
        raise
    finally:
        close_connection(conn)


def print_load_stats(stats):
    print("Database load complete:")
    print(f"  Input records        : {stats['input_records']}")
    print(f"  Inserted records     : {stats['inserted_records']}")
    print(f"  Duplicate records    : {stats['duplicate_records']}")
    print(f"  Failed records       : {stats['failed_records']}")
    print(f"  Database total rows  : {stats['database_total_rows']}")


def print_verify_stats(info):
    if not info["table_exists"]:
        print("Table 'log_events' does not exist. Run db-init first.")
        return

    print("Database verification:")
    print(f"  Table exists     : Yes")
    print(f"  Total rows       : {info['total_rows']}")
    print(f"  Min timestamp    : {info['min_timestamp']}")
    print(f"  Max timestamp    : {info['max_timestamp']}")
    if info["level_counts"]:
        print("  Records by level:")
        for level, count in info["level_counts"].items():
            print(f"    {level}: {count}")
