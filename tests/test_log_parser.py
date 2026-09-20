import unittest

from app.log_parser import parse_log_line, parse_logs, parse_timestamp


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

MALFORMED_LINE = "this is not a valid log line"

SHORT_LINE = "2026-09-20 10:15:32,123 | INFO"

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

DUPLICATE_LINE = (
    "2026-09-20 10:15:32,123 | INFO | API_REQUEST | "
    "service=auth | endpoint=/api/login | method=POST | "
    "status=200 | response_time_ms=142 | user_id=U1024"
)


class TestLogParser(unittest.TestCase):
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

    def test_malformed_record_rejected(self):
        record = parse_log_line(MALFORMED_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("Insufficient", record["rejection_reason"])

    def test_short_line_rejected(self):
        record = parse_log_line(SHORT_LINE)
        self.assertIsNotNone(record["rejection_reason"])

    def test_invalid_timestamp_rejected(self):
        record = parse_log_line(INVALID_TIMESTAMP_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("timestamp", record["rejection_reason"])

    def test_invalid_log_level_rejected(self):
        record = parse_log_line(INVALID_LOG_LEVEL_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("log level", record["rejection_reason"])

    def test_invalid_status_rejected(self):
        record = parse_log_line(INVALID_STATUS_LINE)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("status", record["rejection_reason"])

    def test_negative_response_time_rejected(self):
        record = parse_log_line(NEGATIVE_RESPONSE_TIME)
        self.assertIsNotNone(record["rejection_reason"])
        self.assertIn("response_time_ms", record["rejection_reason"])

    def test_optional_field_absent_not_rejected(self):
        record = parse_log_line(VALID_LOGIN_LINE)
        self.assertIsNone(record["rejection_reason"])
        self.assertIsNone(record["endpoint"])
        self.assertIsNone(record["status"])
        self.assertIsNone(record["response_time_ms"])

    def test_parse_logs_separates_valid_and_rejected(self):
        lines = [VALID_API_LINE, MALFORMED_LINE, VALID_LOGIN_LINE, INVALID_STATUS_LINE]
        parsed, rejected = parse_logs(lines)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len(rejected), 2)

    def test_parse_logs_empty_input(self):
        parsed, rejected = parse_logs([])
        self.assertEqual(len(parsed), 0)
        self.assertEqual(len(rejected), 0)

    def test_parse_timestamp_valid(self):
        ts = parse_timestamp("2026-09-20 10:15:32,123")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)

    def test_parse_timestamp_invalid(self):
        ts = parse_timestamp("not-a-date")
        self.assertIsNone(ts)

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
