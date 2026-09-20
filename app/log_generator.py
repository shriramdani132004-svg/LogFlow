import os
import random
from datetime import datetime, timedelta

from app.config import DEFAULT_RECORD_COUNT, INPUT_DIR, RANDOM_SEED

SERVICES = ["auth", "orders", "payments", "users", "inventory", "notifications"]

ENDPOINTS = {
    "auth": ["/api/login", "/api/logout", "/api/register", "/api/refresh-token"],
    "orders": ["/api/orders", "/api/orders/create", "/api/orders/status"],
    "payments": ["/api/payments", "/api/payments/process", "/api/payments/refund"],
    "users": ["/api/users", "/api/users/profile", "/api/users/update"],
    "inventory": ["/api/inventory", "/api/inventory/check", "/api/inventory/update"],
    "notifications": ["/api/notifications", "/api/notifications/send"],
}

METHODS = ["GET", "POST", "PUT", "DELETE"]

STATUS_WEIGHTS = {
    "auth": [(200, 50), (201, 20), (401, 15), (403, 5), (500, 10)],
    "orders": [(200, 45), (201, 15), (400, 10), (404, 10), (500, 20)],
    "payments": [(200, 40), (201, 20), (400, 15), (500, 25)],
    "users": [(200, 60), (201, 15), (404, 15), (500, 10)],
    "inventory": [(200, 55), (201, 10), (400, 15), (500, 20)],
    "notifications": [(200, 65), (201, 15), (500, 20)],
}

LOG_LEVEL_WEIGHTS = [("DEBUG", 10), ("INFO", 60), ("WARN", 20), ("ERROR", 10)]

USER_IDS = [f"U{str(i).zfill(4)}" for i in range(1000, 1100)]

ERROR_MESSAGES = [
    "Connection refused to database",
    "Timeout waiting for response",
    "Service unavailable",
    "Invalid request body",
    "Permission denied",
    "Resource not found",
    "Internal server error",
    "Rate limit exceeded",
]

CACHE_KEYS = ["user_session", "product_list", "cart_data", "config_cache", "auth_token"]

SERVICE_MESSAGES = {
    "SERVICE_START": "Service started successfully",
    "SERVICE_STOP": "Service shutting down",
}


def _weighted_choice(items_weights, rng):
    items, weights = zip(*items_weights)
    return rng.choices(items, weights=weights, k=1)[0]


def _generate_timestamp(base_time, record_index, total_records, rng):
    spread_seconds = total_records * 0.5
    offset = rng.uniform(0, spread_seconds)
    return base_time + timedelta(seconds=offset)


def _generate_api_request(service, rng):
    endpoint = rng.choice(ENDPOINTS[service])
    method = rng.choice(METHODS)
    status = _weighted_choice(STATUS_WEIGHTS[service], rng)
    response_time = rng.randint(10, 2000)
    user_id = rng.choice(USER_IDS)
    return (
        f"service={service} | endpoint={endpoint} | method={method} "
        f"| status={status} | response_time_ms={response_time} | user_id={user_id}"
    )


def _generate_user_login(rng):
    user_id = rng.choice(USER_IDS)
    ip = f"{rng.randint(10, 192)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    return f"user_id={user_id} | ip={ip} | login_method=password"


def _generate_user_logout(rng):
    user_id = rng.choice(USER_IDS)
    session_duration = rng.randint(60, 7200)
    return f"user_id={user_id} | session_duration_sec={session_duration}"


def _generate_database_query(service, rng):
    query_time = rng.randint(5, 500)
    table = rng.choice(["users", "orders", "payments", "products", "sessions"])
    return f"service={service} | table={table} | query_time_ms={query_time}"


def _generate_database_error(service, rng):
    error = rng.choice(ERROR_MESSAGES)
    query_time = rng.randint(1000, 10000)
    return f"service={service} | error={error} | query_time_ms={query_time}"


def _generate_auth_failure(rng):
    user_id = rng.choice(USER_IDS)
    reason = rng.choice(["invalid_password", "expired_token", "account_locked", "missing_credentials"])
    return f"user_id={user_id} | reason={reason}"


def _generate_cache_access(rng):
    key = rng.choice(CACHE_KEYS)
    hit = rng.choice(["true", "false"])
    ttl = rng.randint(0, 3600)
    return f"key={key} | hit={hit} | ttl_sec={ttl}"


def _generate_service_event(event_type, rng):
    message = SERVICE_MESSAGES[event_type]
    service = rng.choice(SERVICES)
    return f"service={service} | message={message}"


EVENT_GENERATORS = {
    "API_REQUEST": _generate_api_request,
    "USER_LOGIN": _generate_user_login,
    "USER_LOGOUT": _generate_user_logout,
    "DATABASE_QUERY": _generate_database_query,
    "DATABASE_ERROR": _generate_database_error,
    "AUTH_FAILURE": _generate_auth_failure,
    "CACHE_ACCESS": _generate_cache_access,
    "SERVICE_START": _generate_service_event,
    "SERVICE_STOP": _generate_service_event,
}

EVENT_WEIGHTS = [
    ("API_REQUEST", 40),
    ("USER_LOGIN", 10),
    ("USER_LOGOUT", 8),
    ("DATABASE_QUERY", 15),
    ("DATABASE_ERROR", 7),
    ("AUTH_FAILURE", 5),
    ("CACHE_ACCESS", 10),
    ("SERVICE_START", 3),
    ("SERVICE_STOP", 2),
]


def generate_log_line(timestamp, log_level, event_type, service, rng):
    timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") + f",{timestamp.microsecond // 1000:03d}"

    if event_type in ("SERVICE_START", "SERVICE_STOP"):
        detail = _generate_service_event(event_type, rng)
    elif event_type == "API_REQUEST":
        detail = _generate_api_request(service, rng)
    elif event_type == "USER_LOGIN":
        detail = _generate_user_login(rng)
    elif event_type == "USER_LOGOUT":
        detail = _generate_user_logout(rng)
    elif event_type == "DATABASE_QUERY":
        detail = _generate_database_query(service, rng)
    elif event_type == "DATABASE_ERROR":
        detail = _generate_database_error(service, rng)
    elif event_type == "AUTH_FAILURE":
        detail = _generate_auth_failure(rng)
    elif event_type == "CACHE_ACCESS":
        detail = _generate_cache_access(rng)
    else:
        detail = f"service={service}"

    return f"{timestamp_str} | {log_level} | {event_type} | {detail}"


def generate_logs(record_count=None, output_file=None, seed=None):
    if record_count is None:
        record_count = DEFAULT_RECORD_COUNT
    if output_file is None:
        output_file = os.path.join(INPUT_DIR, "application.log")
    if seed is None:
        seed = RANDOM_SEED

    rng = random.Random(seed)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    base_time = datetime(2026, 9, 20, 8, 0, 0)
    lines = []

    for i in range(record_count):
        timestamp = _generate_timestamp(base_time, i, record_count, rng)
        log_level = _weighted_choice(LOG_LEVEL_WEIGHTS, rng)
        event_type = _weighted_choice(EVENT_WEIGHTS, rng)
        service = rng.choice(SERVICES)

        line = generate_log_line(timestamp, log_level, event_type, service, rng)
        lines.append(line)

    lines.sort(key=lambda line: line[:23])

    with open(output_file, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    return record_count, output_file
