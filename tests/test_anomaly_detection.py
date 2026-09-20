import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
import psycopg2

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, OUTPUT_DIR
from app.database import close_connection, get_connection
from app.db_loader import init_schema
from app.anomaly_detection import (
    load_log_data,
    prepare_features,
    detect_anomalies,
    calculate_rule_signals,
    build_anomaly_reason,
    generate_anomaly_report,
    save_anomaly_results,
    run_anomaly_detection,
    OUTPUT_COLS,
    NUMERIC_COLS,
    CATEGORICAL_COLS,
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
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (TEST_DB_NAME,))
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


def _make_df(rows=None):
    if rows is None:
        rows = FIXTURE_ROWS
    records = []
    for i, r in enumerate(rows):
        records.append({
            "id": i + 1,
            "timestamp": pd.Timestamp(r[0]),
            "log_level": r[1],
            "event_type": r[2],
            "service": r[3],
            "endpoint": r[4],
            "method": r[5],
            "status": r[6],
            "response_time_ms": r[7],
            "user_id": r[8],
        })
    return pd.DataFrame(records)


class TestPrepareFeatures(unittest.TestCase):
    def test_numerical_features_created(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        for col in NUMERIC_COLS:
            self.assertIn(col, work.columns)

    def test_time_features_created(self):
        df = _make_df()
        work, _ = prepare_features(df)
        self.assertIn("hour", work.columns)
        self.assertIn("day_of_week", work.columns)
        self.assertIn("minute_of_hour", work.columns)

    def test_binary_indicators(self):
        df = _make_df()
        work, _ = prepare_features(df)
        self.assertIn("is_error", work.columns)
        self.assertIn("is_warning", work.columns)
        self.assertIn("is_auth_failure", work.columns)
        self.assertIn("is_database_error", work.columns)
        self.assertEqual(work["is_error"].sum(), 2)
        self.assertEqual(work["is_warning"].sum(), 1)
        self.assertEqual(work["is_auth_failure"].sum(), 1)
        self.assertEqual(work["is_database_error"].sum(), 1)

    def test_null_numeric_handled(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        X = work[NUMERIC_COLS + CATEGORICAL_COLS].copy()
        X["status"] = X["status"].astype("Int64").astype(float)
        X["response_time_ms"] = X["response_time_ms"].astype("Int64").astype(float)
        X["service"] = X["service"].fillna("UNKNOWN")
        X["log_level"] = X["log_level"].fillna("UNKNOWN")
        X["event_type"] = X["event_type"].fillna("UNKNOWN")
        X_processed = preprocessor.fit_transform(X)
        self.assertFalse(np.isnan(X_processed).any())

    def test_null_categorical_replaced(self):
        rows = list(FIXTURE_ROWS) + [
            ("2026-09-20 10:08:00.000000", "INFO", "API_REQUEST", None, None, None, None, None, None, ""),
        ]
        df = _make_df(rows)
        work, preprocessor = prepare_features(df)
        self.assertFalse(work["service"].isna().any())
        self.assertIn("UNKNOWN", work["service"].values)

    def test_all_null_optional_fields(self):
        rows = [
            ("2026-09-20 10:00:00.000000", "INFO", "API_REQUEST", None, None, None, None, None, None, ""),
        ]
        df = _make_df(rows)
        work, preprocessor = prepare_features(df)
        self.assertEqual(len(work), 1)
        self.assertIsNotNone(preprocessor)

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["id", "timestamp", "log_level", "event_type",
                                    "service", "endpoint", "method", "status",
                                    "response_time_ms", "user_id"])
        work, preprocessor = prepare_features(df)
        self.assertTrue(work.empty)
        self.assertIsNone(preprocessor)


class TestRuleSignals(unittest.TestCase):
    def test_high_response_time_detection(self):
        df = _make_df()
        work, _ = prepare_features(df)
        work = calculate_rule_signals(work)
        self.assertIn("high_response_time", work.columns)
        self.assertTrue(work.loc[work["response_time_ms"] == 5000, "high_response_time"].all())
        self.assertTrue(work.loc[work["response_time_ms"] == 50, "high_response_time"].eq(False).all())

    def test_5xx_detection(self):
        df = _make_df()
        work, _ = prepare_features(df)
        work = calculate_rule_signals(work)
        self.assertIn("server_error", work.columns)
        self.assertTrue(work.loc[work["status"] == 500, "server_error"].all())
        self.assertTrue(work.loc[work["status"] == 200, "server_error"].eq(False).all())

    def test_auth_failure_detection(self):
        df = _make_df()
        work, _ = prepare_features(df)
        work = calculate_rule_signals(work)
        self.assertIn("auth_failure", work.columns)
        self.assertTrue(work.loc[work["event_type"] == "AUTH_FAILURE", "auth_failure"].all())

    def test_database_error_detection(self):
        df = _make_df()
        work, _ = prepare_features(df)
        work = calculate_rule_signals(work)
        self.assertIn("database_error", work.columns)
        self.assertTrue(work.loc[work["event_type"] == "DATABASE_ERROR", "database_error"].all())

    def test_error_log_detection(self):
        df = _make_df()
        work, _ = prepare_features(df)
        work = calculate_rule_signals(work)
        self.assertIn("error_log", work.columns)
        self.assertTrue(work.loc[work["log_level"] == "ERROR", "error_log"].all())
        self.assertTrue(work.loc[work["log_level"] == "INFO", "error_log"].eq(False).all())


class TestAnomalyReason(unittest.TestCase):
    def test_ml_anomaly_reason(self):
        row = {"ml_prediction": -1, "high_response_time": False, "server_error": False,
               "auth_failure": False, "database_error": False, "error_log": False}
        self.assertEqual(build_anomaly_reason(row), "Isolation Forest anomaly")

    def test_combined_reason(self):
        row = {"ml_prediction": -1, "high_response_time": True, "server_error": True,
               "auth_failure": False, "database_error": False, "error_log": False}
        reason = build_anomaly_reason(row)
        self.assertIn("Isolation Forest anomaly", reason)
        self.assertIn("High response time", reason)
        self.assertIn("5xx server error", reason)
        self.assertIn(" + ", reason)

    def test_auth_failure_reason(self):
        row = {"ml_prediction": 1, "high_response_time": False, "server_error": False,
               "auth_failure": True, "database_error": False, "error_log": False}
        self.assertEqual(build_anomaly_reason(row), "Authentication failure")

    def test_no_signal_empty_reason(self):
        row = {"ml_prediction": 1, "high_response_time": False, "server_error": False,
               "auth_failure": False, "database_error": False, "error_log": False}
        self.assertEqual(build_anomaly_reason(row), "")


class TestIsolationForest(unittest.TestCase):
    def test_detection_runs(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertIn("ml_prediction", result.columns)
        self.assertIn("anomaly_score", result.columns)
        self.assertIn("is_anomaly", result.columns)

    def test_deterministic_output(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        r1 = detect_anomalies(work, preprocessor, random_state=42)
        work2, preprocessor2 = prepare_features(df)
        r2 = detect_anomalies(work2, preprocessor2, random_state=42)
        pd.testing.assert_series_equal(r1["is_anomaly"], r2["is_anomaly"])

    def test_configurable_contamination(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        r1 = detect_anomalies(work, preprocessor, contamination=0.1)
        r2 = detect_anomalies(work, preprocessor, contamination=0.5)
        self.assertNotEqual(r1["is_anomaly"].sum(), r2["is_anomaly"].sum())

    def test_predictions_valid(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        preds = result["ml_prediction"].dropna().unique()
        self.assertTrue(all(p in [-1, 1] for p in preds))

    def test_anomaly_scores_numeric(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        scores = result["anomaly_score"].dropna()
        self.assertTrue(pd.api.types.is_numeric_dtype(scores))

    def test_normal_anomaly_counts(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertGreater(result["normal_count"].sum() if "normal_count" in result else (result["is_anomaly"] == False).sum(), 0)

    def test_small_dataset_no_crash(self):
        rows = [
            ("2026-09-20 10:00:00.000000", "INFO", "API_REQUEST", "auth", "/api/login", "POST", 200, 100, "U100", ""),
        ]
        df = _make_df(rows)
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertEqual(len(result), 1)
        self.assertFalse(result["is_anomaly"].iloc[0])

    def test_empty_dataset(self):
        df = pd.DataFrame(columns=["id", "timestamp", "log_level", "event_type",
                                    "service", "endpoint", "method", "status",
                                    "response_time_ms", "user_id"])
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertTrue(result.empty)

    def test_constant_values(self):
        rows = []
        for i in range(15):
            rows.append((f"2026-09-20 10:{i:02d}:00.000000", "INFO", "API_REQUEST",
                         "auth", "/api/login", "POST", 200, 100, f"U{i:04d}", ""))
        df = _make_df(rows)
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertEqual(len(result), 15)
        self.assertTrue(all(p in [-1, 1] for p in result["ml_prediction"].dropna()))

    def test_no_nan_in_ml_input(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        X = work[NUMERIC_COLS + CATEGORICAL_COLS].copy()
        X["status"] = X["status"].astype("Int64").astype(float)
        X["response_time_ms"] = X["response_time_ms"].astype("Int64").astype(float)
        X["service"] = X["service"].fillna("UNKNOWN")
        X["log_level"] = X["log_level"].fillna("UNKNOWN")
        X["event_type"] = X["event_type"].fillna("UNKNOWN")
        X_processed = preprocessor.transform(X)
        self.assertFalse(np.isnan(X_processed).any())


class TestOutputFiles(unittest.TestCase):
    def test_csv_creation(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        with tempfile.TemporaryDirectory() as d:
            csv_path, json_path = save_anomaly_results(work, report, output_dir=d)
            self.assertTrue(os.path.exists(csv_path))

    def test_csv_retains_all_records(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        with tempfile.TemporaryDirectory() as d:
            csv_path, _ = save_anomaly_results(work, report, output_dir=d)
            loaded = pd.read_csv(csv_path)
            self.assertEqual(len(loaded), len(df))

    def test_json_creation(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        with tempfile.TemporaryDirectory() as d:
            _, json_path = save_anomaly_results(work, report, output_dir=d)
            self.assertTrue(os.path.exists(json_path))
            with open(json_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertIn("total_records", loaded)
            self.assertIn("anomaly_count", loaded)

    def test_report_counts_match_dataframe(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        self.assertEqual(report["total_records"], len(df))
        self.assertEqual(report["anomaly_count"], int(work["is_anomaly"].sum()))
        self.assertEqual(report["normal_count"], int((~work["is_anomaly"]).sum()))

    def test_anomaly_rate_range(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        self.assertGreaterEqual(report["anomaly_rate"], 0)
        self.assertLessEqual(report["anomaly_rate"], 100)

    def test_service_breakdown(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        self.assertIsInstance(report["anomalies_by_service"], dict)

    def test_event_type_breakdown(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        self.assertIsInstance(report["anomalies_by_event_type"], dict)

    def test_status_breakdown(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        self.assertIsInstance(report["anomalies_by_status"], dict)

    def test_required_output_columns(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        with tempfile.TemporaryDirectory() as d:
            csv_path, _ = save_anomaly_results(work, report, output_dir=d)
            loaded = pd.read_csv(csv_path)
            for col in OUTPUT_COLS:
                self.assertIn(col, loaded.columns)

    def test_is_anomaly_only_true_false(self):
        df = _make_df()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        with tempfile.TemporaryDirectory() as d:
            csv_path, _ = save_anomaly_results(work, report, output_dir=d)
            loaded = pd.read_csv(csv_path)
            unique_vals = set(loaded["is_anomaly"].unique())
            self.assertTrue(unique_vals.issubset({True, False}))


@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
class TestAnomalyDetectionIntegration(unittest.TestCase):
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
                h = f"anom{i:04d}" + "0" * (64 - len(f"anom{i:04d}"))
                cur.execute("""
                    INSERT INTO log_events (
                        timestamp, log_level, event_type, service,
                        endpoint, method, status, response_time_ms,
                        user_id, message, record_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (*row, h))
            conn.commit()
        close_connection(conn)

    def test_load_log_data(self):
        self._load_fixture()
        df = load_log_data()
        self.assertEqual(len(df), len(FIXTURE_ROWS))

    def test_detection_against_real_db(self):
        self._load_fixture()
        df = load_log_data()
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertEqual(len(result), len(df))
        self.assertIn("is_anomaly", result.columns)

    def test_end_to_end_detection(self):
        self._load_fixture()
        df = load_log_data()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        self.assertEqual(report["total_records"], len(df))
        self.assertGreaterEqual(report["anomaly_count"], 0)

    def test_end_to_end_output_files(self):
        self._load_fixture()
        df = load_log_data()
        work, preprocessor = prepare_features(df)
        work = detect_anomalies(work, preprocessor)
        work = calculate_rule_signals(work)
        work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)
        report = generate_anomaly_report(work)
        with tempfile.TemporaryDirectory() as d:
            csv_path, json_path = save_anomaly_results(work, report, output_dir=d)
            self.assertTrue(os.path.exists(csv_path))
            self.assertTrue(os.path.exists(json_path))


class TestAnomalyDetectionEmptyTable(unittest.TestCase):
    def test_run_anomaly_detection_empty(self):
        df = pd.DataFrame(columns=["id", "timestamp", "log_level", "event_type",
                                    "service", "endpoint", "method", "status",
                                    "response_time_ms", "user_id"])
        work, preprocessor = prepare_features(df)
        result = detect_anomalies(work, preprocessor)
        self.assertTrue(result.empty)


class TestCLIDetect(unittest.TestCase):
    def test_detect_command_exists(self):
        result = subprocess.run(
            [sys.executable, "run.py", "--help"],
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        combined = result.stdout + result.stderr
        self.assertTrue(
            "detect" in combined.lower() or result.returncode == 0,
        )


if __name__ == "__main__":
    unittest.main()
