import unittest

from app.log_generator import EVENT_WEIGHTS
from app.log_parser import (
    parse_log_line,
    parse_logs,
    parse_timestamp,
    VALID_LOG_LEVELS,
    VALID_EVENT_TYPES,
    TIMESTAMP_PATTERN,
    FIELD_PATTERN,
)


VALID_API_LINE = (
    "2026-09-20 10:15:32,123 | INFO | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | "
    "status=200 | response_time_ms=142 | user_id=U1024"
)

VALID_LOGIN_LINE = (
    "2026-09-20 10:15:35,447 | INFO | USER_LOGIN | "
    "user_id=U2048 | ip=192.168.1.100 | login_method=password"
)

VALID_DB_QUERY_LINE = (
    "2026-09-20 10:16:02,901 | WARN | DATABASE_QUERY | "
    "service=orders | table=orders | query_time_ms=450"
)

VALID_SERVICE_LINE = (
    "2026-09-20 08:00:00,000 | INFO | SERVICE_START | "
    "service=auth | message=Service started successfully"
)

VALID_DB_ERROR_LINE = (
    "2026-09-20 10:17:00,000 | ERROR | DATABASE_ERROR | "
    "service=orders | error=Connection refused | query_time_ms=5000"
)

VALID_AUTH_FAILURE_LINE = (
    "2026-09-20 10:18:00,000 | ERROR | AUTH_FAILURE | "
    "user_id=U3000 | reason=invalid_password"
)

VALID_CACHE_ACCESS_LINE = (
    "2026-09-20 10:19:00,000 | DEBUG | CACHE_ACCESS | "
    "key=user_session | hit=true | ttl_sec=300"
)

VALID_USER_LOGOUT_LINE = (
    "2026-09-20 10:20:00,000 | INFO | USER_LOGOUT | "
    "user_id=U4000 | session_duration_sec=1800"
)

VALID_SERVICE_STOP_LINE = (
    "2026-09-20 23:59:59,999 | INFO | SERVICE_STOP | "
    "service=payments | message=Service shutting down"
)

MALFORMED_LINE = "this is not a valid log line"

SHORT_LINE = "2026-09-20 10:15:32,123 | INFO"

EMPTY_LINE = ""

ONLY_PIPES = "|||"

SINGLE_PIPE = "2026-09-20 10:15:32,123"

INVALID_TIMESTAMP_LINE = (
    "not-a-date | INFO | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | status=200"
)

INVALID_LOG_LEVEL_LINE = (
    "2026-09-20 10:15:32,123 | TRACE | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | status=200"
)

INVALID_STATUS_LINE = (
    "2026-09-20 10:15:32,123 | INFO | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | status=abc"
)

NEGATIVE_RESPONSE_TIME = (
    "2026-09-20 10:15:32,123 | INFO | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | "
    "status=200 | response_time_ms=-50 | user_id=U1024"
)

INVALID_EVENT_TYPE_LINE = (
    "2026-09-20 10:15:32,123 | INFO | INVALID_EVENT | "
    "service=auth"
)

DUPLICATE_LINE = (
    "2026-09-20 10:15:32,123 | INFO | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | "
    "status=200 | response_time_ms=142 | user_id=U1024"
)


class TestValidLogLineParsing(unittest.TestCase):
    def test_valid_api_line_parses(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertIsNone(record["rejection_reason"])
        self.assertEqual(record["log_level"], "INFO")
        self.assertEqual(record["event_type"], "API_REQUEST")
        self.assertEqual(record["service"], "auth")
        self.assertEqual(record["endpoint"], "/api/login")
        self.assertEqual(record["method"], "POST")
        self.assertEqual(record["status"], 200)
        self.assertEqual(record["response_time_ms"], 142)
        self.assertEqual(record["user_id"], "U1024")

    def test_timestamp_extracted_correctly(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertIsNotNone(record["timestamp"])
        self.assertEqual(record["timestamp"].year, 2026)
        self.assertEqual(record["timestamp"].month, 9)
        self.assertEqual(record["timestamp"].day, 20)
        self.assertEqual(record["timestamp"].hour, 10)
        self.assertEqual(record["timestamp"].minute, 15)
        self.assertEqual(record["timestamp"].second, 32)
        self.assertEqual(record["timestamp"].microsecond, 123000)

    def test_log_level_extracted(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["log_level"], "INFO")

    def test_event_type_extracted(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["event_type"], "API_REQUEST")

    def test_key_value_fields_extracted(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["service"], "auth")
        self.assertEqual(record["endpoint"], "/api/login")
        self.assertEqual(record["method"], "POST")
        self.assertEqual(record["status"], 200)
        self.assertEqual(record["response_time_ms"], 142)
        self.assertEqual(record["user_id"], "U1024")

    def test_raw_line_preserved(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["raw_line"], VALID_API_LINE)


class TestTimestampParsing(unittest.TestCase):
    def test_timestamp_with_millis(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["timestamp"].microsecond, 123000)

    def test_parse_timestamp_valid(self):
        ts = parse_timestamp("2026-09-20 10:15:32,123")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.microsecond, 123000)

    def test_parse_timestamp_invalid(self):
        ts = parse_timestamp("not-a-date")
        self.assertIsNone(ts)

    def test_parse_timestamp_none(self):
        ts = parse_timestamp(None)
        self.assertIsNone(ts)

    def test_timestamp_pattern_matches_valid(self):
        self.assertIsNotNone(TIMESTAMP_PATTERN.match("2026-09-20 10:15:32,123"))
        self.assertIsNotNone(TIMESTAMP_PATTERN.match("2026-12-31 23:59:59,999"))
        self.assertIsNotNone(TIMESTAMP_PATTERN.match("2026-01-01 00:00:00,000"))

    def test_timestamp_pattern_rejects_invalid(self):
        self.assertIsNone(TIMESTAMP_PATTERN.match("2026-9-20 10:15:32,123"))
        self.assertIsNone(TIMESTAMP_PATTERN.match("2026-09-20 10:15:32"))
        self.assertIsNone(TIMESTAMP_PATTERN.match("2026/09/20 10:15:32,123"))


class TestLogLevels(unittest.TestCase):
    def test_valid_log_levels_defined(self):
        self.assertEqual(VALID_LOG_LEVELS, {"DEBUG", "INFO", "WARN", "ERROR"})

    def test_debug_level_parses(self):
        line = (
            "2026-09-20 10:15:32,123 | DEBUG | API_REQUEST | "
            "service=auth | endpoint=/api/login"
        )
        record = parse_log_line(line)
        self.assertIsNone(record["rejection_reason"])
        self.assertEqual(record["log_level"], "DEBUG")

    def test_info_level_parses(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["log_level"], "INFO")

    def test_warn_level_parses(self):
        record = parse_log_line(VALID_DB_QUERY_LINE)
        self.assertEqual(record["log_level"], "WARN")

    def test_error_level_parses(self):
        record = parse_log_line(VALID_DB_ERROR_LINE)
        self.assertEqual(record["log_level"], "ERROR")

    def test_invalid_log_level_rejected(self):
        record = parse_log_line(INVALID_LOG_LEVEL_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("log level", record["rejection_reason"])

    def test_case_sensitive_log_level(self):
        line = (
            "2026-09-20 10:15:32,123 | info | API_REQUEST | "
            "service=auth"
        )
        record = parse_log_line(line)
        self.assertIsNotNone(record["rejection_reason"])


class TestEventTypes(unittest.TestCase):
    def test_valid_event_types_match_generator(self):
        gen_events = {event for event, _ in EVENT_WEIGHTS}
        self.assertEqual(VALID_EVENT_TYPES, gen_events)

    def test_api_request_parses(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["event_type"], "API_REQUEST")

    def test_user_login_parses(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertEqual(record["event_type"], "USER_LOGIN")

    def test_database_query_parses(self):
        record = parse_log_line(VALID_DB_QUERY_LINE)
        self.assertEqual(record["event_type"], "DATABASE_QUERY")

    def test_database_error_parses(self):
        record = parse_log_line(VALID_DB_ERROR_LINE)
        self.assertEqual(record["event_type"], "DATABASE_ERROR")
        self.assertIsNotNone(record["message"])

    def test_auth_failure_parses(self):
        record = parse_log_line(VALID_AUTH_FAILURE_LINE)
        self.assertEqual(record["event_type"], "AUTH_FAILURE")
        self.assertEqual(record["user_id"], "U3000")
        self.assertIsNotNone(record["message"])

    def test_cache_access_parses(self):
        record = parse_log_line(VALID_CACHE_ACCESS_LINE)
        self.assertEqual(record["event_type"], "CACHE_ACCESS")
        self.assertIsNotNone(record["message"])

    def test_user_logout_parses(self):
        record = parse_log_line(VALID_USER_LOGOUT_LINE)
        self.assertEqual(record["event_type"], "USER_LOGOUT")
        self.assertIsNotNone(record["message"])

    def test_service_start_parses(self):
        record = parse_log_line(VALID_SERVICE_LINE)
        self.assertEqual(record["event_type"], "SERVICE_START")
        self.assertEqual(record["service"], "auth")

    def test_service_stop_parses(self):
        record = parse_log_line(VALID_SERVICE_STOP_LINE)
        self.assertEqual(record["event_type"], "SERVICE_STOP")
        self.assertEqual(record["service"], "payments")

    def test_invalid_event_type_rejected(self):
        record = parse_log_line(INVALID_EVENT_TYPE_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("event type", record["rejection_reason"])


class TestServiceInformation(unittest.TestCase):
    def test_service_from_api_request(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["service"], "auth")

    def test_service_from_database_query(self):
        record = parse_log_line(VALID_DB_QUERY_LINE)
        self.assertEqual(record["service"], "orders")

    def test_service_from_service_start(self):
        record = parse_log_line(VALID_SERVICE_LINE)
        self.assertEqual(record["service"], "auth")

    def test_service_absent_for_user_login(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertIsNone(record["rejection_reason"])


class TestEndpointInformation(unittest.TestCase):
    def test_endpoint_from_api_request(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["endpoint"], "/api/login")

    def test_endpoint_absent_for_user_login(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertIsNone(record["endpoint"])

    def test_method_from_api_request(self):
        record = parse_log_line(VALID_API_LINE)
        self.assertEqual(record["method"], "POST")

    def test_method_absent_for_user_login(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertIsNone(record["method"])


class TestMalformedRecords(unittest.TestCase):
    def test_malformed_record_rejected(self):
        record = parse_log_line(MALFORMED_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("Insufficient", record["rejection_reason"])

    def test_short_line_rejected(self):
        record = parse_log_line(SHORT_LINE)
        self.assertIsNotNone(record["rejection_reason"])

    def test_empty_line_rejected(self):
        record = parse_log_line(EMPTY_LINE)
        self.assertIsNotNone(record["rejection_reason"])

    def test_only_pipes_rejected(self):
        record = parse_log_line(ONLY_PIPES)
        self.assertIsNotNone(record["rejection_reason"])

    def test_single_pipe_rejected(self):
        record = parse_log_line(SINGLE_PIPE)
        self.assertIsNotNone(record["rejection_reason"])

    def test_invalid_timestamp_rejected(self):
        record = parse_log_line(INVALID_TIMESTAMP_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("timestamp", record["rejection_reason"])

    def test_invalid_status_rejected(self):
        record = parse_log_line(INVALID_STATUS_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("status", record["rejection_reason"])

    def test_negative_response_time_rejected(self):
        record = parse_log_line(NEGATIVE_RESPONSE_TIME)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("response_time_ms", record["rejection_reason"])


class TestMissingFields(unittest.TestCase):
    def test_optional_field_absent_not_rejected(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertIsNone(record["rejection_reason"])
        self.assertIsNone(record["endpoint"])
        self.assertIsNone(record["status"])
        self.assertIsNone(record["response_time_ms"])

    def test_message_populated_from_fields(self):
        record = parse_log_line(VALID_DB_ERROR_LINE)
        self.assertIsNotNone(record["message"])
        self.assertIn("error=", record["message"])

    def test_auth_failure_message_populated(self):
        record = parse_log_line(VALID_AUTH_FAILURE_LINE)
        self.assertIsNotNone(record["message"])
        self.assertIn("reason=", record["message"])

    def test_cache_access_message_populated(self):
        record = parse_log_line(VALID_CACHE_ACCESS_LINE)
        self.assertIsNotNone(record["message"])

    def test_logout_message_populated(self):
        record = parse_log_line(VALID_USER_LOGOUT_LINE)
        self.assertIsNotNone(record["message"])


class TestFieldPattern(unittest.TestCase):
    def test_field_pattern_extracts_key_value(self):
        matches = FIELD_PATTERN.findall("service=auth | endpoint=/api/login")
        d = dict(matches)
        self.assertEqual(d["service"], "auth")
        self.assertEqual(d["endpoint"], "/api/login")

    def test_field_pattern_handles_no_trailing_space(self):
        matches = FIELD_PATTERN.findall("service=auth")
        d = dict(matches)
        self.assertEqual(d["service"], "auth")

    def test_field_pattern_handles_values_with_equals(self):
        matches = FIELD_PATTERN.findall("message=error=timeout")
        d = dict(matches)
        self.assertEqual(d["message"], "error=timeout")


class TestParseLogsBatch(unittest.TestCase):
    def test_parse_logs_separates_valid_and_rejected(self):
        lines = [VALID_API_LINE, MALFORMED_LINE, VALID_LOGIN_LINE, INVALID_STATUS_LINE]
        parsed, rejected = parse_logs(lines)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len(rejected), 2)

    def test_parse_logs_empty_input(self):
        parsed, rejected = parse_logs([])
        self.assertEqual(len(parsed), 0)
        self.assertEqual(len(rejected), 0)

    def test_parse_logs_all_valid(self):
        lines = [VALID_API_LINE, VALID_LOGIN_LINE, VALID_DB_QUERY_LINE]
        parsed, rejected = parse_logs(lines)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(len(rejected), 0)

    def test_parse_logs_all_invalid(self):
        lines = [MALFORMED_LINE, SHORT_LINE, INVALID_TIMESTAMP_LINE]
        parsed, rejected = parse_logs(lines)
        self.assertEqual(len(parsed), 0)
        self.assertEqual(len(rejected), 3)

    def test_parse_logs_mixed_event_types(self):
        lines = [
            VALID_API_LINE, VALID_LOGIN_LINE, VALID_DB_QUERY_LINE,
            VALID_DB_ERROR_LINE, VALID_AUTH_FAILURE_LINE, VALID_CACHE_ACCESS_LINE,
        ]
        parsed, rejected = parse_logs(lines)
        self.assertEqual(len(parsed), 6)
        event_types = {r["event_type"] for r in parsed}
        self.assertEqual(len(event_types), 6)

    def test_user_login_parses_without_api_fields(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertIsNone(record["rejection_reason"])
        self.assertEqual(record["event_type"], "USER_LOGIN")
        self.assertEqual(record["user_id"], "U2048")
        self.assertIsNotNone(record["message"])

    def test_database_query_parses(self):
        record = parse_log_line(VALID_DB_QUERY_LINE)
        self.assertIsNone(record["rejection_reason"])
        self.assertEqual(record["event_type"], "DATABASE_QUERY")
        self.assertEqual(record["service"], "orders")
        self.assertIsNotNone(record["message"])

    def test_service_event_parses(self):
        record = parse_log_line(VALID_SERVICE_LINE)
        self.assertIsNone(record["rejection_reason"])
        self.assertEqual(record["event_type"], "SERVICE_START")
        self.assertEqual(record["service"], "auth")


if __name__ == "__main__":
    unittest.main()
