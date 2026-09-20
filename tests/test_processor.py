import os
import tempfile
import unittest

import pandas as pd

from app.log_generator import generate_logs
from app.processor import (
    build_dataframe,
    detect_duplicates,
    format_timestamp,
    process_logs,
    validate_record,
    validate_records,
    OUTPUT_COLUMNS,
    SERVICE_OPTIONAL_EVENTS,
)


VALID_RECORD = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": 142,
    "user_id": "U1024",
    "message": None,
}

RECORD_MISSING_SERVICE = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": None,
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": 142,
    "user_id": "U1024",
    "message": None,
}

RECORD_INVALID_STATUS = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 999,
    "response_time_ms": 142,
    "user_id": "U1024",
    "message": None,
}

RECORD_NEGATIVE_RT = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": -10,
    "user_id": "U1024",
    "message": None,
}

RECORD_OPTIONAL_ABSENT = {
    "timestamp": "2026-09-20 10:15:35,447",
    "log_level": "INFO",
    "event_type": "USER_LOGIN",
    "service": "auth",
    "endpoint": None,
    "method": None,
    "status": None,
    "response_time_ms": None,
    "user_id": "U2048",
    "message": "ip=192.168.1.100; login_method=password",
}

RECORD_MISSING_TIMESTAMP = {
    "timestamp": None,
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": 100,
    "user_id": "U1000",
    "message": None,
}

RECORD_MISSING_LOG_LEVEL = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": None,
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": 100,
    "user_id": "U1000",
    "message": None,
}

RECORD_MISSING_EVENT_TYPE = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": None,
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": 100,
    "user_id": "U1000",
    "message": None,
}

RECORD_STATUS_BOUNDARY_LOW = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 100,
    "response_time_ms": 50,
    "user_id": "U1000",
    "message": None,
}

RECORD_STATUS_BOUNDARY_HIGH = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 599,
    "response_time_ms": 50,
    "user_id": "U1000",
    "message": None,
}

RECORD_STATUS_TOO_LOW = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 99,
    "response_time_ms": 50,
    "user_id": "U1000",
    "message": None,
}

RECORD_STATUS_TOO_HIGH = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 600,
    "response_time_ms": 50,
    "user_id": "U1000",
    "message": None,
}

RECORD_RT_ZERO = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": 0,
    "user_id": "U1000",
    "message": None,
}

RECORD_NON_INT_STATUS = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": "abc",
    "response_time_ms": 100,
    "user_id": "U1000",
    "message": None,
}

RECORD_NON_INT_RT = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "API_REQUEST",
    "service": "auth",
    "endpoint": "/api/login",
    "method": "POST",
    "status": 200,
    "response_time_ms": "abc",
    "user_id": "U1000",
    "message": None,
}

RECORD_OPTIONAL_SERVICE_EVENTS = {
    "timestamp": "2026-09-20 10:15:32,123",
    "log_level": "INFO",
    "event_type": "USER_LOGIN",
    "service": None,
    "endpoint": None,
    "method": None,
    "status": None,
    "response_time_ms": None,
    "user_id": "U1000",
    "message": None,
}


class TestValidation(unittest.TestCase):
    def test_valid_record_passes(self):
        errors = validate_record(VALID_RECORD)
        self.assertEqual(errors, [])

    def test_missing_timestamp_rejected(self):
        errors = validate_record(RECORD_MISSING_TIMESTAMP)
        self.assertTrue(any("timestamp" in e for e in errors))

    def test_missing_log_level_rejected(self):
        errors = validate_record(RECORD_MISSING_LOG_LEVEL)
        self.assertTrue(any("log_level" in e for e in errors))

    def test_missing_event_type_rejected(self):
        errors = validate_record(RECORD_MISSING_EVENT_TYPE)
        self.assertTrue(any("event_type" in e for e in errors))

    def test_missing_service_rejected(self):
        errors = validate_record(RECORD_MISSING_SERVICE)
        self.assertTrue(any("service" in e for e in errors))

    def test_invalid_status_rejected(self):
        errors = validate_record(RECORD_INVALID_STATUS)
        self.assertTrue(any("status" in e for e in errors))

    def test_negative_response_time_rejected(self):
        errors = validate_record(RECORD_NEGATIVE_RT)
        self.assertTrue(any("response_time_ms" in e for e in errors))

    def test_optional_absent_not_rejected(self):
        errors = validate_record(RECORD_OPTIONAL_ABSENT)
        self.assertEqual(errors, [])

    def test_status_boundary_low_passes(self):
        errors = validate_record(RECORD_STATUS_BOUNDARY_LOW)
        self.assertEqual(errors, [])

    def test_status_boundary_high_passes(self):
        errors = validate_record(RECORD_STATUS_BOUNDARY_HIGH)
        self.assertEqual(errors, [])

    def test_status_below_100_rejected(self):
        errors = validate_record(RECORD_STATUS_TOO_LOW)
        self.assertTrue(any("status" in e for e in errors))

    def test_status_above_599_rejected(self):
        errors = validate_record(RECORD_STATUS_TOO_HIGH)
        self.assertTrue(any("status" in e for e in errors))

    def test_zero_response_time_passes(self):
        errors = validate_record(RECORD_RT_ZERO)
        self.assertEqual(errors, [])

    def test_non_int_status_rejected(self):
        errors = validate_record(RECORD_NON_INT_STATUS)
        self.assertTrue(any("status" in e for e in errors))

    def test_non_int_response_time_rejected(self):
        errors = validate_record(RECORD_NON_INT_RT)
        self.assertTrue(any("response_time_ms" in e for e in errors))

    def test_optional_service_event_no_service_needed(self):
        errors = validate_record(RECORD_OPTIONAL_SERVICE_EVENTS)
        self.assertEqual(errors, [])

    def test_optional_events_definition(self):
        self.assertIn("USER_LOGIN", SERVICE_OPTIONAL_EVENTS)
        self.assertIn("USER_LOGOUT", SERVICE_OPTIONAL_EVENTS)
        self.assertIn("AUTH_FAILURE", SERVICE_OPTIONAL_EVENTS)
        self.assertIn("CACHE_ACCESS", SERVICE_OPTIONAL_EVENTS)

    def test_validate_records_separates_valid_invalid(self):
        records = [VALID_RECORD, RECORD_MISSING_SERVICE, RECORD_OPTIONAL_ABSENT]
        valid, invalid = validate_records(records)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 1)

    def test_validate_records_all_valid(self):
        records = [VALID_RECORD, RECORD_OPTIONAL_ABSENT]
        valid, invalid = validate_records(records)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 0)

    def test_validate_records_all_invalid(self):
        records = [RECORD_MISSING_SERVICE, RECORD_INVALID_STATUS, RECORD_NEGATIVE_RT]
        valid, invalid = validate_records(records)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(invalid), 3)


class TestBuildDataframe(unittest.TestCase):
    def test_build_dataframe_has_expected_columns(self):
        df = build_dataframe([VALID_RECORD])
        self.assertEqual(list(df.columns), OUTPUT_COLUMNS)

    def test_build_dataframe_empty_input(self):
        df = build_dataframe([])
        self.assertTrue(df.empty)
        self.assertEqual(list(df.columns), OUTPUT_COLUMNS)

    def test_build_dataframe_preserves_data(self):
        df = build_dataframe([VALID_RECORD])
        self.assertEqual(df.iloc[0]["log_level"], "INFO")
        self.assertEqual(df.iloc[0]["event_type"], "API_REQUEST")
        self.assertEqual(df.iloc[0]["service"], "auth")

    def test_build_dataframe_multiple_records(self):
        records = [VALID_RECORD, RECORD_OPTIONAL_ABSENT]
        df = build_dataframe(records)
        self.assertEqual(len(df), 2)

    def test_build_dataframe_missing_columns_get_none(self):
        record = {"timestamp": "2026-09-20 10:00:00,000", "log_level": "INFO",
                  "event_type": "API_REQUEST", "service": "auth"}
        df = build_dataframe([record])
        self.assertEqual(list(df.columns), OUTPUT_COLUMNS)
        self.assertIsNone(df.iloc[0]["endpoint"])

    def test_build_dataframe_preserves_none_values(self):
        record = VALID_RECORD.copy()
        record["endpoint"] = None
        record["method"] = None
        df = build_dataframe([record])
        self.assertIsNone(df.iloc[0]["endpoint"])
        self.assertIsNone(df.iloc[0]["method"])


class TestDuplicates(unittest.TestCase):
    def test_no_duplicates(self):
        df = build_dataframe([VALID_RECORD, RECORD_OPTIONAL_ABSENT])
        df_deduped, count = detect_duplicates(df)
        self.assertEqual(count, 0)
        self.assertEqual(len(df_deduped), 2)

    def test_detects_duplicates(self):
        df = build_dataframe([VALID_RECORD, VALID_RECORD.copy()])
        df_deduped, count = detect_duplicates(df)
        self.assertEqual(count, 1)
        self.assertEqual(len(df_deduped), 1)

    def test_empty_dataframe(self):
        df = build_dataframe([])
        df_deduped, count = detect_duplicates(df)
        self.assertEqual(count, 0)
        self.assertTrue(df_deduped.empty)

    def test_multiple_duplicates(self):
        df = build_dataframe([VALID_RECORD, VALID_RECORD.copy(), VALID_RECORD.copy()])
        df_deduped, count = detect_duplicates(df)
        self.assertEqual(count, 2)
        self.assertEqual(len(df_deduped), 1)

    def test_near_duplicates_not_removed(self):
        r1 = VALID_RECORD.copy()
        r2 = VALID_RECORD.copy()
        r2["status"] = 201
        df = build_dataframe([r1, r2])
        df_deduped, count = detect_duplicates(df)
        self.assertEqual(count, 0)
        self.assertEqual(len(df_deduped), 2)


class TestFormatTimestamp(unittest.TestCase):
    def test_format_none(self):
        self.assertIsNone(format_timestamp(None))

    def test_format_nan(self):
        self.assertIsNone(format_timestamp(float("nan")))

    def test_format_pandas_timestamp(self):
        ts = pd.Timestamp("2026-09-20 10:15:32.123000")
        result = format_timestamp(ts)
        self.assertIn("2026-09-20", result)
        self.assertIn(",", result)

    def test_format_string_passthrough(self):
        result = format_timestamp("2026-09-20 10:15:32,123")
        self.assertEqual(result, "2026-09-20 10:15:32,123")


class TestProcessPipeline(unittest.TestCase):
    def _run_process(self, log_content, tmpdir):
        log_file = os.path.join(tmpdir, "test.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_content)

        cleaned_path = os.path.join(tmpdir, "cleaned_logs.csv")
        rejected_path = os.path.join(tmpdir, "rejected_logs.csv")

        import app.processor as proc
        orig_cleaned = proc.CLEANED_OUTPUT
        orig_rejected = proc.REJECTED_OUTPUT
        proc.CLEANED_OUTPUT = cleaned_path
        proc.REJECTED_OUTPUT = rejected_path

        try:
            return process_logs(input_file=log_file)
        finally:
            proc.CLEANED_OUTPUT = orig_cleaned
            proc.REJECTED_OUTPUT = orig_rejected

    def test_process_generates_cleaned_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=50, output_file=log_file, seed=42)

            cleaned_path = os.path.join(tmpdir, "cleaned_logs.csv")
            rejected_path = os.path.join(tmpdir, "rejected_logs.csv")

            import app.processor as proc
            orig_cleaned = proc.CLEANED_OUTPUT
            orig_rejected = proc.REJECTED_OUTPUT
            proc.CLEANED_OUTPUT = cleaned_path
            proc.REJECTED_OUTPUT = rejected_path

            try:
                df, stats, _, _ = process_logs(input_file=log_file)
                self.assertTrue(os.path.exists(cleaned_path))
                self.assertTrue(os.path.exists(rejected_path))
                self.assertEqual(stats["cleaned_records"], len(df))
                self.assertGreater(stats["total_raw"], 0)
            finally:
                proc.CLEANED_OUTPUT = orig_cleaned
                proc.REJECTED_OUTPUT = orig_rejected

    def test_cleaned_csv_has_structured_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=20, output_file=log_file, seed=42)

            cleaned_path = os.path.join(tmpdir, "cleaned_logs.csv")
            rejected_path = os.path.join(tmpdir, "rejected_logs.csv")

            import app.processor as proc
            orig_cleaned = proc.CLEANED_OUTPUT
            orig_rejected = proc.REJECTED_OUTPUT
            proc.CLEANED_OUTPUT = cleaned_path
            proc.REJECTED_OUTPUT = rejected_path

            try:
                df, _, _, _ = process_logs(input_file=log_file)
                self.assertEqual(list(df.columns), OUTPUT_COLUMNS)
            finally:
                proc.CLEANED_OUTPUT = orig_cleaned
                proc.REJECTED_OUTPUT = orig_rejected

    def test_rejected_csv_has_reasons(self):
        content = (
            "2026-09-20 10:15:32,123 | INFO | API_REQUEST | service=auth | endpoint=/api/login | method=POST | status=200 | response_time_ms=142 | user_id=U1024\n"
            "this is garbage\n"
            "also bad\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            df, stats, _, _ = self._run_process(content, tmpdir)
            rejected_path = os.path.join(tmpdir, "rejected_logs.csv")
            rejected_df = pd.read_csv(rejected_path)
            self.assertGreater(len(rejected_df), 0)
            self.assertIn("rejection_reason", rejected_df.columns)
            self.assertIn("raw_line", rejected_df.columns)

    def test_statistics_are_consistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=100, output_file=log_file, seed=42)

            cleaned_path = os.path.join(tmpdir, "cleaned_logs.csv")
            rejected_path = os.path.join(tmpdir, "rejected_logs.csv")

            import app.processor as proc
            orig_cleaned = proc.CLEANED_OUTPUT
            orig_rejected = proc.REJECTED_OUTPUT
            proc.CLEANED_OUTPUT = cleaned_path
            proc.REJECTED_OUTPUT = rejected_path

            try:
                _, stats, _, _ = process_logs(input_file=log_file)
                total_accounted = (
                    stats["cleaned_records"]
                    + stats["malformed_records"]
                    + stats["validation_failures"]
                    + stats["duplicate_records"]
                )
                self.assertGreaterEqual(total_accounted, stats["total_raw"])
            finally:
                proc.CLEANED_OUTPUT = orig_cleaned
                proc.REJECTED_OUTPUT = orig_rejected

    def test_empty_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            df, stats, _, _ = self._run_process("", tmpdir)
            self.assertEqual(stats["total_raw"], 0)
            self.assertEqual(stats["cleaned_records"], 0)

    def test_all_malformed_input(self):
        content = "not a log line\nalso not a log line\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            df, stats, _, _ = self._run_process(content, tmpdir)
            self.assertEqual(stats["cleaned_records"], 0)
            self.assertGreater(stats["malformed_records"], 0)

    def test_mixed_valid_and_invalid(self):
        content = (
            "2026-09-20 10:15:32,123 | INFO | API_REQUEST | service=auth | endpoint=/api/login | method=POST | status=200 | response_time_ms=142 | user_id=U1024\n"
            "garbage line\n"
            "2026-09-20 10:16:00,000 | WARN | DATABASE_QUERY | service=orders | table=users | query_time_ms=50\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            df, stats, _, _ = self._run_process(content, tmpdir)
            self.assertEqual(stats["cleaned_records"], 2)
            self.assertEqual(stats["malformed_records"], 1)

    def test_deterministic_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            generate_logs(record_count=50, output_file=log_file, seed=42)

            import app.processor as proc
            results = []
            for i in range(2):
                cleaned_path = os.path.join(tmpdir, f"cleaned_{i}.csv")
                rejected_path = os.path.join(tmpdir, f"rejected_{i}.csv")
                orig_cleaned = proc.CLEANED_OUTPUT
                orig_rejected = proc.REJECTED_OUTPUT
                proc.CLEANED_OUTPUT = cleaned_path
                proc.REJECTED_OUTPUT = rejected_path
                try:
                    _, stats, _, _ = process_logs(input_file=log_file)
                    results.append(stats)
                finally:
                    proc.CLEANED_OUTPUT = orig_cleaned
                    proc.REJECTED_OUTPUT = orig_rejected

            self.assertEqual(results[0]["cleaned_records"], results[1]["cleaned_records"])
            self.assertEqual(results[0]["malformed_records"], results[1]["malformed_records"])


if __name__ == "__main__":
    unittest.main()
