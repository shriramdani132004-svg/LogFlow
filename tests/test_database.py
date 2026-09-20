import csv
import os
import tempfile
import unittest
from datetime import datetime

from app.db_loader import (
    compute_record_hash,
    convert_csv_value,
    normalize_timestamp_for_hash,
    parse_timestamp,
    prepare_rows,
    validate_csv_columns,
)


class TestParseTimestamp(unittest.TestCase):
    def test_comma_fractional_seconds(self):
        ts = parse_timestamp("2026-09-20 10:15:32,123")
        self.assertEqual(ts, datetime(2026, 9, 20, 10, 15, 32, 123000))

    def test_comma_six_digits(self):
        ts = parse_timestamp("2026-09-20 10:15:32,123456")
        self.assertEqual(ts, datetime(2026, 9, 20, 10, 15, 32, 123456))

    def test_dot_fractional_seconds(self):
        ts = parse_timestamp("2026-09-20 10:15:32.123")
        self.assertEqual(ts, datetime(2026, 9, 20, 10, 15, 32, 123000))

    def test_dot_six_digits(self):
        ts = parse_timestamp("2026-09-20 10:15:32.123456")
        self.assertEqual(ts, datetime(2026, 9, 20, 10, 15, 32, 123456))

    def test_basic_timestamp(self):
        ts = parse_timestamp("2026-09-20 10:15:32")
        self.assertEqual(ts, datetime(2026, 9, 20, 10, 15, 32))

    def test_datetime_object_unchanged(self):
        dt = datetime(2026, 9, 20, 10, 15, 32, 123000)
        self.assertEqual(parse_timestamp(dt), dt)

    def test_none_returns_none(self):
        self.assertIsNone(parse_timestamp(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_timestamp(""))

    def test_whitespace_returns_none(self):
        self.assertIsNone(parse_timestamp("   "))

    def test_whitespace_trimmed(self):
        ts = parse_timestamp("  2026-09-20 10:15:32,123  ")
        self.assertEqual(ts, datetime(2026, 9, 20, 10, 15, 32, 123000))

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            parse_timestamp("not-a-date")

    def test_integer_type_raises(self):
        with self.assertRaises(ValueError):
            parse_timestamp(12345)


class TestNormalizeTimestampForHash(unittest.TestCase):
    def test_datetime_to_string(self):
        dt = datetime(2026, 9, 20, 10, 15, 32, 123000)
        result = normalize_timestamp_for_hash(dt)
        self.assertEqual(result, "2026-09-20 10:15:32.123000")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_timestamp_for_hash(None), "")

    def test_string_normalized_to_dot_format(self):
        result = normalize_timestamp_for_hash("2026-09-20 10:15:32,123")
        self.assertEqual(result, "2026-09-20 10:15:32.123000")

    def test_string_matches_datetime_normalization(self):
        from app.db_loader import normalize_timestamp_for_hash as ntfh
        s_result = ntfh("2026-09-20 10:15:32,123")
        d_result = ntfh(datetime(2026, 9, 20, 10, 15, 32, 123000))
        self.assertEqual(s_result, d_result)


class TestComputeRecordHash(unittest.TestCase):
    def _make_row(self, ts_val):
        return {
            "timestamp": ts_val,
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

    def test_same_input_same_hash(self):
        row = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        self.assertEqual(compute_record_hash(row), compute_record_hash(row))

    def test_different_status_different_hash(self):
        r1 = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        r2 = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        r2["status"] = 404
        self.assertNotEqual(compute_record_hash(r1), compute_record_hash(r2))

    def test_hash_is_64_char_hex(self):
        h = compute_record_hash(self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000)))
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_none_values_deterministic(self):
        row = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        row["service"] = None
        row["endpoint"] = None
        self.assertEqual(compute_record_hash(row), compute_record_hash(row))

    def test_whitespace_normalized(self):
        r1 = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        r1["log_level"] = "  INFO  "
        r1["service"] = "  auth  "
        r2 = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        self.assertEqual(compute_record_hash(r1), compute_record_hash(r2))

    def test_hash_deterministic_across_formats(self):
        r1 = self._make_row("2026-09-20 10:15:32,123")
        r2 = self._make_row(datetime(2026, 9, 20, 10, 15, 32, 123000))
        self.assertEqual(compute_record_hash(r1), compute_record_hash(r2))


class TestConvertCsvValue(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(convert_csv_value(None, "status"))

    def test_empty_returns_none(self):
        self.assertIsNone(convert_csv_value("", "status"))

    def test_nan_returns_none(self):
        self.assertIsNone(convert_csv_value("NaN", "status"))

    def test_nat_returns_none(self):
        self.assertIsNone(convert_csv_value("NaT", "timestamp"))

    def test_status_to_int(self):
        self.assertEqual(convert_csv_value("200", "status"), 200)

    def test_response_time_to_int(self):
        self.assertEqual(convert_csv_value("142", "response_time_ms"), 142)

    def test_string_preserved(self):
        self.assertEqual(convert_csv_value("auth", "service"), "auth")

    def test_whitespace_stripped(self):
        self.assertEqual(convert_csv_value("  INFO  ", "log_level"), "INFO")

    def test_timestamp_as_string(self):
        result = convert_csv_value("2026-09-20 10:15:32,123", "timestamp")
        self.assertEqual(result, "2026-09-20 10:15:32,123")


class TestValidateCsvColumns(unittest.TestCase):
    def test_valid_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "log_level", "event_type", "service",
                             "endpoint", "method", "status", "response_time_ms",
                             "user_id", "message"])
            self.assertEqual(len(validate_csv_columns(p)), 10)

    def test_missing_column_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            with open(p, "w", newline="") as f:
                csv.writer(f).writerow(["timestamp", "log_level"])
            with self.assertRaises(ValueError):
                validate_csv_columns(p)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            validate_csv_columns("/nonexistent/file.csv")

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            open(p, "w").close()
            with self.assertRaises(ValueError):
                validate_csv_columns(p)


class TestPrepareRows(unittest.TestCase):
    def _write_csv(self, path, rows):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "log_level", "event_type", "service",
                         "endpoint", "method", "status", "response_time_ms",
                         "user_id", "message"])
            for r in rows:
                w.writerow(r)

    def test_comma_timestamp_converted_to_datetime(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["2026-09-20 10:15:32,123", "INFO", "API_REQUEST",
                                  "auth", "/api/login", "POST", "200", "142",
                                  "U1024", ""]])
            rows = prepare_rows(p)
            self.assertIsInstance(rows[0]["timestamp"], datetime)
            self.assertEqual(rows[0]["timestamp"], datetime(2026, 9, 20, 10, 15, 32, 123000))

    def test_dot_timestamp_converted_to_datetime(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["2026-09-20 10:15:32.123", "INFO", "API_REQUEST",
                                  "auth", "/api/login", "POST", "200", "142",
                                  "U1024", ""]])
            rows = prepare_rows(p)
            self.assertIsInstance(rows[0]["timestamp"], datetime)

    def test_null_values_converted(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["2026-09-20 10:15:32,123", "INFO", "USER_LOGIN",
                                  "", "", "", "", "", "U2048", ""]])
            rows = prepare_rows(p)
            self.assertIsNone(rows[0]["service"])
            self.assertIsNone(rows[0]["status"])

    def test_invalid_timestamp_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["not-a-date", "INFO", "API_REQUEST",
                                  "auth", "", "", "", "", "", ""]])
            with self.assertRaises(ValueError):
                prepare_rows(p)

    def test_missing_timestamp_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["", "INFO", "API_REQUEST",
                                  "auth", "", "", "", "", "", ""]])
            with self.assertRaises(ValueError):
                prepare_rows(p)

    def test_record_hash_present(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["2026-09-20 10:15:32,123", "INFO", "API_REQUEST",
                                  "auth", "/api/login", "POST", "200", "142",
                                  "U1024", ""]])
            rows = prepare_rows(p)
            self.assertIn("record_hash", rows[0])
            self.assertEqual(len(rows[0]["record_hash"]), 64)

    def test_special_characters_in_message(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            self._write_csv(p, [["2026-09-20 10:15:32,123", "ERROR", "API_REQUEST",
                                  "auth", "/api/login", "POST", "500", "1500",
                                  "U1024", "error=it's broken; retry(3)"]])
            rows = prepare_rows(p)
            self.assertIn("it's broken", rows[0]["message"])


if __name__ == "__main__":
    unittest.main()
