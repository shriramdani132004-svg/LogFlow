import os

import pandas as pd

from app.config import INPUT_DIR, OUTPUT_DIR, RAW_LOG_FILE
from app.ingestion import ingest_logs
from app.log_parser import parse_logs, REQUIRED_FIELDS

CLEANED_OUTPUT = os.path.join(OUTPUT_DIR, "cleaned_logs.csv")
REJECTED_OUTPUT = os.path.join(OUTPUT_DIR, "rejected_logs.csv")

OUTPUT_COLUMNS = [
    "timestamp", "log_level", "event_type", "service",
    "endpoint", "method", "status", "response_time_ms",
    "user_id", "message",
]


SERVICE_OPTIONAL_EVENTS = {"USER_LOGIN", "USER_LOGOUT", "AUTH_FAILURE", "CACHE_ACCESS"}


def validate_record(record):
    errors = []

    if record.get("timestamp") is None:
        errors.append("Missing required field: timestamp")

    if record.get("log_level") is None:
        errors.append("Missing required field: log_level")

    if record.get("event_type") is None:
        errors.append("Missing required field: event_type")

    event_type = record.get("event_type")
    if record.get("service") is None and event_type not in SERVICE_OPTIONAL_EVENTS:
        errors.append("Missing required field: service")

    if record.get("status") is not None:
        if not isinstance(record["status"], int):
            errors.append(f"Invalid status type: {record['status']}")
        elif record["status"] < 100 or record["status"] > 599:
            errors.append(f"Out-of-range status: {record['status']}")

    if record.get("response_time_ms") is not None:
        if not isinstance(record["response_time_ms"], int):
            errors.append(f"Invalid response_time_ms type: {record['response_time_ms']}")
        elif record["response_time_ms"] < 0:
            errors.append(f"Negative response_time_ms: {record['response_time_ms']}")

    return errors


def validate_records(parsed_records):
    valid = []
    invalid = []
    for record in parsed_records:
        errors = validate_record(record)
        if errors:
            record["rejection_reason"] = "; ".join(errors)
            invalid.append(record)
        else:
            valid.append(record)
    return valid, invalid


def build_dataframe(records):
    if not records:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = pd.DataFrame(records)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[OUTPUT_COLUMNS]


def detect_duplicates(df):
    if df.empty:
        return df, 0

    subset_cols = [
        "timestamp", "log_level", "event_type", "service",
        "endpoint", "method", "status", "response_time_ms",
        "user_id", "message",
    ]
    existing_cols = [c for c in subset_cols if c in df.columns]

    before = len(df)
    df_deduped = df.drop_duplicates(subset=existing_cols, keep="first").reset_index(drop=True)
    duplicates_removed = before - len(df_deduped)
    return df_deduped, duplicates_removed


def format_timestamp(ts):
    if pd.isna(ts) or ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.strftime("%Y-%m-%d %H:%M:%S") + f",{ts.microsecond // 1000:03d}"
    return str(ts)


def process_logs(input_file=None):
    if input_file is None:
        input_file = RAW_LOG_FILE

    raw_records, ingestion_stats = ingest_logs(input_file)
    total_raw = len(raw_records)

    parsed_records, parse_rejections = parse_logs(raw_records)
    total_parsed = len(parsed_records)
    total_parse_rejected = len(parse_rejections)

    valid_records, validation_rejections = validate_records(parsed_records)
    total_validation_rejected = len(validation_rejections)

    all_rejections = parse_rejections + validation_rejections

    df = build_dataframe(valid_records)
    df, duplicates_removed = detect_duplicates(df)

    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].apply(format_timestamp)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df.to_csv(CLEANED_OUTPUT, index=False)

    rejected_df = pd.DataFrame([{
        "raw_line": r.get("raw_line", ""),
        "rejection_reason": r.get("rejection_reason", ""),
    } for r in all_rejections])
    rejected_df.to_csv(REJECTED_OUTPUT, index=False)

    stats = {
        "total_raw": total_raw,
        "successfully_parsed": total_parsed,
        "malformed_records": total_parse_rejected,
        "validation_failures": total_validation_rejected,
        "duplicate_records": duplicates_removed,
        "cleaned_records": len(df),
    }

    return df, stats, CLEANED_OUTPUT, REJECTED_OUTPUT


def print_processing_stats(stats):
    print("Processing complete:")
    print(f"  Raw records             : {stats['total_raw']}")
    print(f"  Successfully parsed     : {stats['successfully_parsed']}")
    print(f"  Malformed records       : {stats['malformed_records']}")
    print(f"  Validation failures     : {stats['validation_failures']}")
    print(f"  Duplicate records       : {stats['duplicate_records']}")
    print(f"  Cleaned records         : {stats['cleaned_records']}")
