import json
import os
import tempfile
import unittest
from datetime import datetime

import psycopg2

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, OUTPUT_DIR
from app.database import close_connection, get_connection
from app.db_loader import init_schema
from app.analytics import (
    get_overall_summary,
    get_log_level_distribution,
    get_event_type_distribution,
    get_service_distribution,
    get_status_distribution,
    get_status_class_distribution,
    get_error_summary,
    get_response_time_summary,
    get_slowest_endpoints,
    get_most_used_endpoints,
    get_service_performance,
    get_hourly_traffic,
    get_user_activity_summary,
    run_all_analytics,
    save_report,
    print_report,
    _fmt,
    _fmt_pct,
    _fmt_ms,
    _NA,
)


def postgres_available():
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname="postgres",
            user=DB_USER, password=DB_PASSWORD,
        )
        close_connection(conn)
        return True
    except Exception:
        return False


TEST_DB_NAME = "logflow_test"


def create_test_database():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname="postgres",
        user=DB_USER, password=DB_PASSWORD,
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
    exists = cur.fetchone()
    if not exists:
        cur.execute("CREATE DATABASE " + TEST_DB_NAME)
    close_connection(conn)


def drop_test_database():
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname="postgres",
            user=DB_USER, password=DB_PASSWORD,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
        """, (TEST_DB_NAME,))
        cur.execute("DROP DATABASE IF EXISTS " + TEST_DB_NAME)
        close_connection(conn)
    except Exception:
        pass


def clean_test_table():
    try:
        conn = get_connection()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM log_events")
        close_connection(conn)
    except Exception:
        pass


FIXTURE_ROWS = [
    ("2026-09-20 10:00:00.000000", "INFO", "API_REQUEST", "auth", "/api/login", "POST", 200, 100, "U100", ""),
    ("2026-09-20 10:01:00.000000", "INFO", "API_REQUEST", "auth", "/api/login", "POST", 200, 120, "U100", ""),
    ("2026-09-20 10:02:00.000000", "ERROR", "API_REQUEST", "auth", "/api/login", "POST", 500, 2000, "U101", "timeout"),
    ("2026-09-20 10:03:00.000000", "WARN", "API_REQUEST", "payments", "/api/pay", "POST", 400, 80, "U102", ""),
    ("2026-09-20 10:04:00.000000", "INFO", "USER_LOGIN", "auth", None, None, None, None, "U100", ""),
    ("2026-09-20 10:05:00.000000", "ERROR", "DATABASE_ERROR", "orders", None, None, None, 5000, None, "connection refused"),
    ("2026-09-20 10:06:00.000000", "DEBUG", "API_REQUEST", "auth", "/api/users", "GET", 200, 50, "U103", ""),
    ("2026-09-20 10:07:00.000000", "INFO", "AUTH_FAILURE", "auth", "/api/login", "POST", 401, 90, "U104", "bad credentials"),
]

HASHES = [
    "a" * 64, "b" * 64, "c" * 64, "d" * 64,
    "e" * 64, "f" * 64, "0" * 64, "1" * 64,
]


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestAnalyticsFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.config as cfg
        cls._orig_db = cfg.DB_NAME
        create_test_database()
        cfg.DB_NAME = TEST_DB_NAME
        init_schema()

    @classmethod
    def tearDownClass(cls):
        import app.config as cfg
        cfg.DB_NAME = cls._orig_db
        drop_test_database()

    def setUp(self):
        clean_test_table()
        conn = get_connection()
        with conn.cursor() as cur:
            for i, row in enumerate(FIXTURE_ROWS):
                cur.execute("""
                    INSERT INTO log_events (
                        timestamp, log_level, event_type, service,
                        endpoint, method, status, response_time_ms,
                        user_id, message, record_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (*row, HASHES[i]))
            conn.commit()
        close_connection(conn)

    def test_overall_summary(self):
        result = get_overall_summary()
        self.assertEqual(result["total_records"], 8)
        self.assertIsNotNone(result["earliest_timestamp"])
        self.assertIsNotNone(result["latest_timestamp"])

    def test_log_level_distribution(self):
        result = get_log_level_distribution()
        self.assertEqual(len(result), 4)
        levels = {r["log_level"]: r["event_count"] for r in result}
        self.assertEqual(levels["INFO"], 4)
        self.assertEqual(levels["ERROR"], 2)
        self.assertEqual(levels["WARN"], 1)
        self.assertEqual(levels["DEBUG"], 1)
        total_pct = sum(r["pct"] for r in result)
        self.assertAlmostEqual(total_pct, 100.0, delta=1)

    def test_event_type_distribution(self):
        result = get_event_type_distribution()
        self.assertGreater(len(result), 0)
        types = {r["event_type"]: r["event_count"] for r in result}
        self.assertEqual(types["API_REQUEST"], 5)
        self.assertEqual(types["USER_LOGIN"], 1)
        self.assertEqual(types["DATABASE_ERROR"], 1)
        self.assertEqual(types["AUTH_FAILURE"], 1)

    def test_service_distribution(self):
        result = get_service_distribution()
        self.assertGreater(len(result), 0)
        services = {r["service"]: r["event_count"] for r in result}
        self.assertEqual(services["auth"], 6)
        self.assertEqual(services["payments"], 1)
        self.assertEqual(services["orders"], 1)

    def test_status_distribution(self):
        result = get_status_distribution()
        self.assertGreater(len(result), 0)
        statuses = {r["status"]: r["event_count"] for r in result}
        self.assertEqual(statuses[200], 3)
        self.assertEqual(statuses[500], 1)
        self.assertEqual(statuses[400], 1)
        self.assertEqual(statuses[401], 1)

    def test_status_class_distribution(self):
        result = get_status_class_distribution()
        classes = {r["status_class"]: r["event_count"] for r in result}
        self.assertEqual(classes.get("2xx", 0), 3)
        self.assertEqual(classes.get("4xx", 0), 2)
        self.assertEqual(classes.get("5xx", 0), 1)
        self.assertEqual(classes.get("other", 0), 2)

    def test_error_summary(self):
        result = get_error_summary()
        self.assertEqual(result["total_errors"], 2)
        self.assertEqual(result["total_warnings"], 1)
        self.assertEqual(result["auth_failures"], 1)
        self.assertEqual(result["database_errors"], 1)

    def test_response_time_summary(self):
        result = get_response_time_summary()
        self.assertIsNotNone(result["avg_response_time_ms"])
        self.assertAlmostEqual(float(result["avg_response_time_ms"]), 1062.86, delta=0.1)
        self.assertEqual(result["min_response_time_ms"], 50)
        self.assertEqual(result["max_response_time_ms"], 5000)
        self.assertEqual(result["samples"], 7)

    def test_slowest_endpoints(self):
        result = get_slowest_endpoints()
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["endpoint"], "/api/login")
        self.assertEqual(result[0]["avg_response_time_ms"], 577.5)
        for r in result:
            self.assertIn("endpoint", r)
            self.assertIn("request_count", r)
            self.assertIn("avg_response_time_ms", r)
            self.assertIn("max_response_time_ms", r)

    def test_most_used_endpoints(self):
        result = get_most_used_endpoints()
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["endpoint"], "/api/login")
        self.assertEqual(result[0]["request_count"], 4)
        for r in result:
            self.assertIn("endpoint", r)
            self.assertIn("request_count", r)
            self.assertIn("avg_response_time_ms", r)

    def test_service_performance(self):
        result = get_service_performance()
        self.assertGreater(len(result), 0)
        auth = [r for r in result if r["service"] == "auth"][0]
        self.assertEqual(auth["total_count"], 6)
        self.assertEqual(auth["error_count"], 1)

    def test_hourly_traffic(self):
        result = get_hourly_traffic()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["event_count"], 8)

    def test_user_activity_summary(self):
        result = get_user_activity_summary()
        self.assertGreater(len(result), 0)
        users = {r["user_id"]: r["event_count"] for r in result}
        self.assertEqual(users["U100"], 3)
        self.assertEqual(users["U101"], 1)
        for r in result:
            self.assertIn("user_id", r)
            self.assertIn("event_count", r)
            self.assertIn("pct", r)

    def test_run_all_analytics(self):
        result = run_all_analytics()
        expected_keys = [
            "overall_summary", "log_level_distribution", "event_type_distribution",
            "service_distribution", "status_distribution", "status_class_distribution",
            "error_summary", "response_time_summary", "slowest_endpoints",
            "most_used_endpoints", "service_performance", "hourly_traffic",
            "user_activity_summary",
        ]
        for key in expected_keys:
            self.assertIn(key, result)


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestAnalyticsEmptyTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.config as cfg
        cls._orig_db = cfg.DB_NAME
        create_test_database()
        cfg.DB_NAME = TEST_DB_NAME
        init_schema()

    @classmethod
    def tearDownClass(cls):
        import app.config as cfg
        cfg.DB_NAME = cls._orig_db
        drop_test_database()

    def setUp(self):
        clean_test_table()

    def test_overall_summary_empty(self):
        result = get_overall_summary()
        self.assertEqual(result["total_records"], 0)
        self.assertIsNone(result["earliest_timestamp"])
        self.assertIsNone(result["latest_timestamp"])

    def test_log_level_distribution_empty(self):
        result = get_log_level_distribution()
        self.assertEqual(result, [])

    def test_event_type_distribution_empty(self):
        result = get_event_type_distribution()
        self.assertEqual(result, [])

    def test_service_distribution_empty(self):
        result = get_service_distribution()
        self.assertEqual(result, [])

    def test_status_distribution_empty(self):
        result = get_status_distribution()
        self.assertEqual(result, [])

    def test_status_class_distribution_empty(self):
        result = get_status_class_distribution()
        self.assertEqual(result, [])

    def test_error_summary_empty(self):
        result = get_error_summary()
        self.assertEqual(result["total_errors"], 0)
        self.assertEqual(result["total_warnings"], 0)
        self.assertEqual(result["auth_failures"], 0)
        self.assertEqual(result["database_errors"], 0)

    def test_response_time_summary_empty(self):
        result = get_response_time_summary()
        self.assertIsNone(result["avg_response_time_ms"])
        self.assertIsNone(result["min_response_time_ms"])
        self.assertIsNone(result["max_response_time_ms"])
        self.assertEqual(result["samples"], 0)

    def test_slowest_endpoints_empty(self):
        result = get_slowest_endpoints()
        self.assertEqual(result, [])

    def test_most_used_endpoints_empty(self):
        result = get_most_used_endpoints()
        self.assertEqual(result, [])

    def test_service_performance_empty(self):
        result = get_service_performance()
        self.assertEqual(result, [])

    def test_hourly_traffic_empty(self):
        result = get_hourly_traffic()
        self.assertEqual(result, [])

    def test_user_activity_summary_empty(self):
        result = get_user_activity_summary()
        self.assertEqual(result, [])

    def test_run_all_analytics_empty(self):
        result = run_all_analytics()
        self.assertEqual(result["overall_summary"]["total_records"], 0)
        self.assertEqual(result["log_level_distribution"], [])


class TestAnalyticsJSONReport(unittest.TestCase):
    def test_save_report(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "analytics_report.json")
            data = {
                "overall_summary": {"total_records": 0, "earliest_timestamp": None, "latest_timestamp": None},
                "log_level_distribution": [],
                "error_summary": {"total_errors": 0, "total_warnings": 0, "auth_failures": 0, "database_errors": 0},
            }
            save_report(data, path)
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["overall_summary"]["total_records"], 0)
            self.assertEqual(loaded["log_level_distribution"], [])

    def test_save_report_with_datetime(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "analytics_report.json")
            data = {
                "overall_summary": {
                    "total_records": 1,
                    "earliest_timestamp": datetime(2026, 1, 1, 0, 0, 0),
                    "latest_timestamp": datetime(2026, 1, 2, 0, 0, 0),
                },
            }
            save_report(data, path)
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["overall_summary"]["earliest_timestamp"], "2026-01-01T00:00:00")


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestAnalyticsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.config as cfg
        cls._orig_db = cfg.DB_NAME
        create_test_database()
        cfg.DB_NAME = TEST_DB_NAME
        init_schema()

    @classmethod
    def tearDownClass(cls):
        import app.config as cfg
        cfg.DB_NAME = cls._orig_db
        drop_test_database()

    def setUp(self):
        clean_test_table()

    def _load_fixture(self):
        conn = get_connection()
        with conn.cursor() as cur:
            for i, row in enumerate(FIXTURE_ROWS):
                cur.execute("""
                    INSERT INTO log_events (
                        timestamp, log_level, event_type, service,
                        endpoint, method, status, response_time_ms,
                        user_id, message, record_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (*row, HASHES[i]))
            conn.commit()
        close_connection(conn)

    def test_full_analytics_after_load(self):
        self._load_fixture()
        data = run_all_analytics()
        self.assertEqual(data["overall_summary"]["total_records"], 8)
        self.assertEqual(data["error_summary"]["total_errors"], 2)
        self.assertGreater(data["response_time_summary"]["samples"], 0)
        self.assertGreater(len(data["slowest_endpoints"]), 0)
        self.assertGreater(len(data["most_used_endpoints"]), 0)

    def test_analytics_then_load_then_analytics(self):
        data1 = run_all_analytics()
        self.assertEqual(data1["overall_summary"]["total_records"], 0)
        self._load_fixture()
        data2 = run_all_analytics()
        self.assertEqual(data2["overall_summary"]["total_records"], 8)

    def test_json_report_after_load(self):
        self._load_fixture()
        data = run_all_analytics()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "analytics_report.json")
            save_report(data, path)
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["overall_summary"]["total_records"], 8)


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestAnalyticsSQLFile(unittest.TestCase):
    def test_analytics_sql_file_exists(self):
        sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql", "analytics.sql")
        self.assertTrue(os.path.exists(sql_path))


class TestFormatHelpers(unittest.TestCase):
    def test_fmt_none_no_width(self):
        self.assertEqual(_fmt(None), _NA)

    def test_fmt_none_with_width(self):
        self.assertEqual(_fmt(None, 10), _NA.ljust(10))

    def test_fmt_value_no_width(self):
        self.assertEqual(_fmt("hello"), "hello")

    def test_fmt_value_with_width(self):
        self.assertEqual(_fmt("hi", 10), "hi" + " " * 8)

    def test_fmt_int(self):
        self.assertEqual(_fmt(42), "42")

    def test_fmt_pct_none(self):
        self.assertEqual(_fmt_pct(None), "N/A")

    def test_fmt_pct_value(self):
        self.assertEqual(_fmt_pct(50.0), "50.0")

    def test_fmt_ms_none(self):
        self.assertEqual(_fmt_ms(None), "N/A")

    def test_fmt_ms_value(self):
        self.assertEqual(_fmt_ms(123), "123")

    def test_fmt_zero(self):
        self.assertEqual(_fmt(0), "0")

    def test_fmt_empty_string(self):
        self.assertEqual(_fmt(""), "")


NULL_FIXTURE_ROWS = [
    ("2026-09-20 10:00:00.000000", "INFO", "API_REQUEST", "auth", "/api/login", "POST", 200, 100, None, ""),
    ("2026-09-20 10:01:00.000000", "ERROR", "USER_LOGIN", None, None, None, None, None, "U200", "timeout"),
    ("2026-09-20 10:02:00.000000", "INFO", "API_REQUEST", "auth", "/api/pay", "GET", 200, 80, None, ""),
    ("2026-09-20 10:03:00.000000", "WARN", "DATABASE_ERROR", None, None, None, 500, 3000, "U200", "conn lost"),
]

NULL_HASHES = ["aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32]


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestAnalyticsNULLHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.config as cfg
        cls._orig_db = cfg.DB_NAME
        create_test_database()
        cfg.DB_NAME = TEST_DB_NAME
        init_schema()

    @classmethod
    def tearDownClass(cls):
        import app.config as cfg
        cfg.DB_NAME = cls._orig_db
        drop_test_database()

    def setUp(self):
        clean_test_table()

    def _load_null_fixture(self):
        conn = get_connection()
        with conn.cursor() as cur:
            for i, row in enumerate(NULL_FIXTURE_ROWS):
                cur.execute("""
                    INSERT INTO log_events (
                        timestamp, log_level, event_type, service,
                        endpoint, method, status, response_time_ms,
                        user_id, message, record_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (*row, NULL_HASHES[i]))
            conn.commit()
        close_connection(conn)

    def test_service_distribution_with_null_service(self):
        self._load_null_fixture()
        result = get_service_distribution()
        services = {r["service"]: r["event_count"] for r in result}
        self.assertIn(None, services)
        self.assertEqual(services[None], 2)
        self.assertEqual(services["auth"], 2)

    def test_status_distribution_with_null_status(self):
        self._load_null_fixture()
        result = get_status_distribution()
        statuses = {r["status"]: r["event_count"] for r in result}
        self.assertIn(None, statuses)
        self.assertEqual(statuses[None], 1)

    def test_status_class_with_null_status(self):
        self._load_null_fixture()
        result = get_status_class_distribution()
        classes = {r["status_class"]: r["event_count"] for r in result}
        self.assertEqual(classes.get("2xx", 0), 2)
        self.assertEqual(classes.get("other", 0), 1)
        self.assertEqual(classes.get("5xx", 0), 1)

    def test_user_activity_with_null_user_id(self):
        self._load_null_fixture()
        result = get_user_activity_summary()
        users = {r["user_id"]: r["event_count"] for r in result}
        self.assertEqual(users["U200"], 2)
        self.assertNotIn(None, users)

    def test_response_time_with_nulls(self):
        self._load_null_fixture()
        result = get_response_time_summary()
        self.assertEqual(result["samples"], 3)

    def test_service_performance_with_nulls(self):
        self._load_null_fixture()
        result = get_service_performance()
        services = {r["service"]: r for r in result}
        self.assertNotIn(None, services)
        self.assertEqual(services["auth"]["total_count"], 2)

    def test_slowest_endpoints_excludes_null_endpoint(self):
        self._load_null_fixture()
        result = get_slowest_endpoints()
        for r in result:
            self.assertIsNotNone(r["endpoint"])

    def test_most_used_endpoints_excludes_null_endpoint(self):
        self._load_null_fixture()
        result = get_most_used_endpoints()
        for r in result:
            self.assertIsNotNone(r["endpoint"])

    def test_print_report_with_null_service(self):
        self._load_null_fixture()
        data = run_all_analytics()
        import io
        import sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_report(data)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn("## Service Distribution", output)
        self.assertIn("N/A", output)
        self.assertNotIn("unsupported format", output.lower())
        self.assertNotIn("Traceback", output)

    def test_print_report_with_null_endpoint(self):
        self._load_null_fixture()
        data = run_all_analytics()
        import io
        import sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_report(data)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn("## Slowest Endpoints", output)
        self.assertIn("## Most-Used Endpoints", output)

    def test_print_report_with_null_response_time(self):
        self._load_null_fixture()
        data = run_all_analytics()
        import io
        import sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_report(data)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn("## Response Time", output)
        self.assertIn("## Service Performance", output)

    def test_json_report_with_null_values(self):
        self._load_null_fixture()
        data = run_all_analytics()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "analytics_report.json")
            save_report(data, path)
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            svc_dist = loaded["service_distribution"]
            services = {r["service"]: r["event_count"] for r in svc_dist}
            self.assertIn(None, services)

    def test_run_all_analytics_with_nulls(self):
        self._load_null_fixture()
        data = run_all_analytics()
        self.assertGreater(data["overall_summary"]["total_records"], 0)
        self.assertIn(None, {r["service"] for r in data["service_distribution"]})


class TestPrintReportEmptyData(unittest.TestCase):
    def test_print_report_with_empty_data(self):
        data = {
            "overall_summary": {"total_records": 0, "earliest_timestamp": None, "latest_timestamp": None},
            "log_level_distribution": [],
            "event_type_distribution": [],
            "service_distribution": [],
            "status_distribution": [],
            "status_class_distribution": [],
            "error_summary": {"total_errors": 0, "total_warnings": 0, "auth_failures": 0, "database_errors": 0},
            "response_time_summary": {"avg_response_time_ms": None, "min_response_time_ms": None, "max_response_time_ms": None, "samples": 0},
            "slowest_endpoints": [],
            "most_used_endpoints": [],
            "service_performance": [],
            "hourly_traffic": [],
            "user_activity_summary": [],
        }
        import io
        import sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_report(data)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()
        self.assertIn("## Analytics Summary", output)
        self.assertIn("N/A", output)
        self.assertIn("0", output)

    def test_print_report_with_all_none_values(self):
        data = {
            "overall_summary": {"total_records": 0, "earliest_timestamp": None, "latest_timestamp": None},
            "log_level_distribution": [],
            "event_type_distribution": [],
            "service_distribution": [],
            "status_distribution": [],
            "status_class_distribution": [],
            "error_summary": {"total_errors": 0, "total_warnings": 0, "auth_failures": 0, "database_errors": 0},
            "response_time_summary": {"avg_response_time_ms": None, "min_response_time_ms": None, "max_response_time_ms": None, "samples": 0},
            "slowest_endpoints": [],
            "most_used_endpoints": [],
            "service_performance": [],
            "hourly_traffic": [],
            "user_activity_summary": [],
        }
        import io
        import sys
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_report(data)
        finally:
            sys.stdout = old_stdout
        self.assertIn("N/A", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
