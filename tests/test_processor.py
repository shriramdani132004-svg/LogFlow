import os
import tempfile
import unittest

import pandas as pd

from app.log_generator import generate_logs
from app.processor import (
    build_dataframe,
    detect_duplicates,
    process_logs,
    validate_record,
    validate_records,
    OUTPUT_COLUMNS,
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


class TestValidation(unittest.TestCase):
    def test_valid_record_passes(self):
        errors = validate_record(VALID_RECORD)
        self.assertEqual(errors, [])

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

    def test_validate_records_separates_valid_invalid(self):
        records = [VALID_RECORD, RECORD_MISSING_SERVICE, RECORD_OPTIONAL_ABSENT]
        valid, invalid = validate_records(records)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 1)


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


class TestProcessPipeline(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            with open(log_file, "w") as f:
                f.write("2026-09-20 10:15:32,123 | INFO | API_REQUEST | service=auth | endpoint=/api/login | method=POST | status=200 | response_time_ms=142 | user_id=U1024\n")
                f.write("this is garbage\n")
                f.write("also bad\n")

            cleaned_path = os.path.join(tmpdir, "cleaned_logs.csv")
            rejected_path = os.path.join(tmpdir, "rejected_logs.csv")

            import app.processor as proc
            orig_cleaned = proc.CLEANED_OUTPUT
            orig_rejected = proc.REJECTED_OUTPUT
            proc.CLEANED_OUTPUT = cleaned_path
            proc.REJECTED_OUTPUT = rejected_path

            try:
                _, stats, _, _ = process_logs(input_file=log_file)
                rejected_df = pd.read_csv(rejected_path)
                self.assertGreater(len(rejected_df), 0)
                self.assertIn("rejection_reason", rejected_df.columns)
                self.assertIn("raw_line", rejected_df.columns)
            finally:
                proc.CLEANED_OUTPUT = orig_cleaned
                proc.REJECTED_OUTPUT = orig_rejected

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


if __name__ == "__main__":
    unittest.main()
