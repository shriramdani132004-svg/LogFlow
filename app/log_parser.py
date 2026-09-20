import re
from datetime import datetime

from app.log_generator import SERVICES, EVENT_WEIGHTS

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}

VALID_EVENT_TYPES = {event for event, _ in EVENT_WEIGHTS}

REQUIRED_FIELDS = {"timestamp", "log_level", "event_type", "service"}

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}$")

FIELD_PATTERN = re.compile(r"(\w+)=(.+?)(?= \| |$)")


def parse_timestamp(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")
    except (ValueError, TypeError):
        return None


def parse_log_line(line):
    result = {
        "raw_line": line,
        "timestamp": None,
        "log_level": None,
        "event_type": None,
        "service": None,
        "endpoint": None,
        "method": None,
        "status": None,
        "response_time_ms": None,
        "user_id": None,
        "message": None,
        "rejection_reason": None,
    }

    parts = [p.strip() for p in line.split("|")]

    if len(parts) < 4:
        result["rejection_reason"] = "Insufficient pipe-delimited sections"
        return result

    timestamp_str = parts[0]
    if not TIMESTAMP_PATTERN.match(timestamp_str):
        result["rejection_reason"] = f"Invalid timestamp format: {timestamp_str}"
        return result

    ts = parse_timestamp(timestamp_str)
    if ts is None:
        result["rejection_reason"] = f"Cannot parse timestamp: {timestamp_str}"
        return result
    result["timestamp"] = ts

    log_level = parts[1]
    if log_level not in VALID_LOG_LEVELS:
        result["rejection_reason"] = f"Invalid log level: {log_level}"
        return result
    result["log_level"] = log_level

    event_type = parts[2]
    if event_type not in VALID_EVENT_TYPES:
        result["rejection_reason"] = f"Invalid event type: {event_type}"
        return result
    result["event_type"] = event_type

    detail_section = " | ".join(parts[3:])
    fields = dict(FIELD_PATTERN.findall(detail_section))

    if "service" in fields:
        result["service"] = fields["service"]
    elif event_type in ("SERVICE_START", "SERVICE_STOP"):
        result["service"] = fields.get("service")
    else:
        for key in ("service",):
            if key in fields:
                result["service"] = fields[key]
                break

    if "endpoint" in fields:
        result["endpoint"] = fields["endpoint"]
    if "method" in fields:
        result["method"] = fields["method"]
    if "status" in fields:
        try:
            result["status"] = int(fields["status"])
        except ValueError:
            result["rejection_reason"] = f"Invalid status value: {fields['status']}"
            return result
    if "response_time_ms" in fields:
        try:
            rt = int(fields["response_time_ms"])
            if rt < 0:
                result["rejection_reason"] = f"Negative response_time_ms: {rt}"
                return result
            result["response_time_ms"] = rt
        except ValueError:
            result["rejection_reason"] = f"Invalid response_time_ms: {fields['response_time_ms']}"
            return result
    if "user_id" in fields:
        result["user_id"] = fields["user_id"]

    message_parts = []
    for key in ("error", "message", "reason", "table", "key", "hit", "ttl_sec",
                 "ip", "login_method", "session_duration_sec", "query_time_ms"):
        if key in fields:
            message_parts.append(f"{key}={fields[key]}")
    if message_parts:
        result["message"] = "; ".join(message_parts)

    return result


def parse_logs(raw_lines):
    parsed = []
    rejected = []
    for line in raw_lines:
        record = parse_log_line(line)
        if record["rejection_reason"]:
            rejected.append(record)
        else:
            parsed.append(record)
    return parsed, rejected
