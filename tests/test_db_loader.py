import csv
import os
import tempfile
import unittest
from datetime import datetime

import psycopg2

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from app.database import close_connection, get_connection
from app.db_loader import (
    load_csv_to_db,
    init_schema,
    prepare_rows,
    verify_database,
)
from app.log_generator import generate_logs
from app.processor import process_logs


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


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestDatabaseConnection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.config as cfg
        cls._orig_db = cfg.DB_NAME
        create_test_database()
        cfg.DB_NAME = TEST_DB_NAME

    @classmethod
    def tearDownClass(cls):
        import app.config as cfg
        cfg.DB_NAME = cls._orig_db
        drop_test_database()

    def test_connection(self):
        conn = get_connection()
        self.assertIsNotNone(conn)
        self.assertFalse(conn.closed)
        close_connection(conn)

    def test_connection_cleanup(self):
        conn = get_connection()
        close_connection(conn)
        self.assertTrue(conn.closed)


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestSchemaCreation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app.config as cfg
        cls._orig_db = cfg.DB_NAME
        create_test_database()
        cfg.DB_NAME = TEST_DB_NAME

    @classmethod
    def tearDownClass(cls):
        import app.config as cfg
        cfg.DB_NAME = cls._orig_db
        drop_test_database()

    def test_schema_creation(self):
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'log_events'
            )
        """)
        self.assertTrue(cur.fetchone()[0])
        close_connection(conn)

    def test_schema_idempotent(self):
        init_schema()
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'log_events'
            )
        """)
        self.assertTrue(cur.fetchone()[0])
        close_connection(conn)

    def test_required_columns(self):
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'log_events' ORDER BY ordinal_position
        """)
        columns = {row[0] for row in cur.fetchall()}
        close_connection(conn)
        expected = {"id", "timestamp", "log_level", "event_type", "service",
                     "endpoint", "method", "status", "response_time_ms",
                     "user_id", "message", "record_hash"}
        self.assertTrue(expected.issubset(columns))

    def test_primary_key(self):
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'log_events' AND constraint_type = 'PRIMARY KEY'
        """)
        self.assertIsNotNone(cur.fetchone())
        close_connection(conn)

    def test_unique_hash_constraint(self):
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'log_events' AND constraint_type = 'UNIQUE'
        """)
        constraints = [row[0] for row in cur.fetchall()]
        close_connection(conn)
        self.assertTrue(any("hash" in c.lower() for c in constraints))

    def test_check_constraints(self):
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT constraint_name FROM information_schema.check_constraints
            WHERE constraint_name LIKE 'chk_%%'
        """)
        checks = {row[0] for row in cur.fetchall()}
        close_connection(conn)
        self.assertIn("chk_log_level", checks)
        self.assertIn("chk_response_time", checks)
        self.assertIn("chk_status", checks)

    def test_indexes(self):
        init_schema()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'log_events'")
        indexes = {row[0] for row in cur.fetchall()}
        close_connection(conn)
        self.assertTrue(any("timestamp" in idx for idx in indexes))
        self.assertTrue(any("log_level" in idx for idx in indexes))


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestDatabaseLoading(unittest.TestCase):
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

    def _make_csv(self, tmpdir, rows):
        csv_path = os.path.join(tmpdir, "test.csv")
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "log_level", "event_type", "service",
                         "endpoint", "method", "status", "response_time_ms",
                         "user_id", "message"])
            for row in rows:
                w.writerow(row)
        return csv_path

    def test_first_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "INFO", "API_REQUEST", "auth",
                 "/api/login", "POST", "200", "142", "U1024", ""],
            ])
            stats = load_csv_to_db(p)
            self.assertEqual(stats["inserted_records"], 1)

    def test_row_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "INFO", "API_REQUEST", "auth",
                 "/api/login", "POST", "200", "142", "U1024", ""],
            ])
            load_csv_to_db(p)
            info = verify_database()
            self.assertEqual(info["total_rows"], 1)

    def test_repeat_load_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "INFO", "API_REQUEST", "auth",
                 "/api/login", "POST", "200", "142", "U1024", ""],
            ])
            s1 = load_csv_to_db(p)
            s2 = load_csv_to_db(p)
            self.assertEqual(s1["inserted_records"], 1)
            self.assertEqual(s2["inserted_records"], 0)
            self.assertEqual(s2["duplicate_records"], 1)
            info = verify_database()
            self.assertEqual(info["total_rows"], 1)

    def test_three_times_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "INFO", "API_REQUEST", "auth",
                 "/api/login", "POST", "200", "142", "U1024", ""],
            ])
            load_csv_to_db(p)
            load_csv_to_db(p)
            s = load_csv_to_db(p)
            self.assertEqual(s["inserted_records"], 0)
            self.assertEqual(s["duplicate_records"], 1)
            info = verify_database()
            self.assertEqual(info["total_rows"], 1)

    def test_empty_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [])
            stats = load_csv_to_db(p)
            self.assertEqual(stats["input_records"], 0)

    def test_null_fields_stored(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "INFO", "USER_LOGIN", "",
                 "", "", "", "", "U1024", ""],
            ])
            load_csv_to_db(p)
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT service, endpoint, method, status FROM log_events")
            row = cur.fetchone()
            close_connection(conn)
            self.assertIsNone(row[0])
            self.assertIsNone(row[1])
            self.assertIsNone(row[2])
            self.assertIsNone(row[3])

    def test_special_characters(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "ERROR", "API_REQUEST", "auth",
                 "/api/login", "POST", "500", "1500", "U1024",
                 "error=it's broken; retry(3)"],
            ])
            load_csv_to_db(p)
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT message FROM log_events")
            msg = cur.fetchone()[0]
            close_connection(conn)
            self.assertIn("it's broken", msg)

    def test_timestamp_is_datetime_in_db(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32,123", "INFO", "API_REQUEST", "auth",
                 "/api/login", "POST", "200", "142", "U1024", ""],
            ])
            load_csv_to_db(p)
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT timestamp FROM log_events")
            ts = cur.fetchone()[0]
            close_connection(conn)
            self.assertIsInstance(ts, datetime)

    def test_dot_timestamp_loads(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make_csv(d, [
                ["2026-09-20 10:15:32.456", "INFO", "API_REQUEST", "auth",
                 "/api/login", "POST", "200", "142", "U1024", ""],
            ])
            stats = load_csv_to_db(p)
            self.assertEqual(stats["inserted_records"], 1)

    def test_missing_csv_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_csv_to_db("/nonexistent/file.csv")

    def test_missing_columns_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.csv")
            with open(p, "w", newline="") as f:
                csv.writer(f).writerow(["col1", "col2"])
                csv.writer(f).writerow(["a", "b"])
            with self.assertRaises(ValueError):
                load_csv_to_db(p)


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestDatabaseVerify(unittest.TestCase):
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

    def test_verify_empty(self):
        info = verify_database()
        self.assertTrue(info["table_exists"])
        self.assertEqual(info["total_rows"], 0)

    def test_verify_with_data(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "log_level", "event_type", "service",
                             "endpoint", "method", "status", "response_time_ms",
                             "user_id", "message"])
                w.writerow(["2026-09-20 10:15:32,123", "INFO", "API_REQUEST", "auth",
                             "/api/login", "POST", "200", "142", "U1024", ""])
                w.writerow(["2026-09-20 10:16:00,000", "ERROR", "DATABASE_ERROR", "orders",
                             "", "", "500", "5000", "", "timeout"])
            load_csv_to_db(p)
            info = verify_database()
            self.assertEqual(info["total_rows"], 2)
            self.assertIsNotNone(info["min_timestamp"])
            self.assertIsNotNone(info["max_timestamp"])
            self.assertIn("INFO", info["level_counts"])
            self.assertIn("ERROR", info["level_counts"])


if __name__ == "__main__":
    unittest.main()
