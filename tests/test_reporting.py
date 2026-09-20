import csv
import json
import os
import tempfile
import unittest

import pandas as pd

from app.reporting import (
    generate_data_quality_report,
    generate_operational_report,
    generate_top_findings,
    generate_final_report,
    save_final_reports,
    _load_anomaly_report,
)
from app.config import OUTPUT_DIR


def _make_sample_df(n=10):
    rows = []
    for i in range(n):
        rows.append({
            "id": i + 1,
            "timestamp": f"2026-09-20 10:{i:02d}:00",
            "log_level": ["INFO", "ERROR", "WARN", "DEBUG"][i % 4],
            "event_type": "API_REQUEST",
            "service": "auth" if i % 2 == 0 else "payments",
            "endpoint": "/api/login",
            "method": "POST",
            "status": 200 if i % 3 != 0 else 500,
            "response_time_ms": 100 + i * 10,
            "user_id": f"U{i:04d}",
        })
    return pd.DataFrame(rows)


class TestDataQualityReport(unittest.TestCase):
    def test_total_record_calculation(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        self.assertEqual(report["total_records"], 5)

    def test_duplicate_detection(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        dup_check = [c for c in report["checks"] if c["check_name"] == "duplicate_ids"][0]
        self.assertEqual(dup_check["status"], "PASS")
        self.assertEqual(dup_check["value"], 0)

    def test_null_counting(self):
        df = _make_sample_df(5)
        df.loc[0, "service"] = None
        report = generate_data_quality_report(df)
        svc_check = [c for c in report["checks"] if c["check_name"] == "service_completeness"][0]
        self.assertEqual(svc_check["value"], 1)

    def test_required_field_validation(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        for field in ["timestamp", "log_level", "event_type"]:
            check = [c for c in report["checks"] if c["check_name"] == f"{field}_completeness"][0]
            self.assertEqual(check["status"], "PASS")

    def test_response_time_validation(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        check = [c for c in report["checks"] if c["check_name"] == "negative_response_times"][0]
        self.assertEqual(check["status"], "PASS")

    def test_http_status_validation(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        check = [c for c in report["checks"] if c["check_name"] == "invalid_http_status"][0]
        self.assertEqual(check["status"], "PASS")

    def test_quality_score_calculation(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        self.assertGreater(report["quality_score"], 0)
        self.assertLessEqual(report["quality_score"], 100)

    def test_pass_warn_fail_generation(self):
        df = _make_sample_df(5)
        report = generate_data_quality_report(df)
        statuses = {c["status"] for c in report["checks"]}
        self.assertIn("PASS", statuses)

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["id", "timestamp", "log_level", "event_type",
                                    "service", "endpoint", "method", "status",
                                    "response_time_ms", "user_id"])
        report = generate_data_quality_report(df)
        self.assertEqual(report["total_records"], 0)
        self.assertGreaterEqual(report["quality_score"], 0.0)


class TestOperationalReport(unittest.TestCase):
    def test_operational_report_generation(self):
        report = generate_operational_report()
        self.assertIn("total_events", report)
        self.assertIn("error_count", report)
        self.assertIn("anomaly_count", report)

    def test_operational_report_reuses_analytics(self):
        report = generate_operational_report()
        self.assertIn("log_level_distribution", report)
        self.assertIn("service_performance", report)


class TestFinalReport(unittest.TestCase):
    def test_final_report_generation(self):
        report = generate_final_report()
        self.assertIn("generated_at", report)
        self.assertIn("dataset", report)
        self.assertIn("data_quality", report)
        self.assertIn("operational_metrics", report)
        self.assertIn("anomaly_detection", report)
        self.assertIn("top_findings", report)

    def test_dynamic_top_findings(self):
        report = generate_final_report()
        self.assertIsInstance(report["top_findings"], list)
        self.assertGreater(len(report["top_findings"]), 0)

    def test_json_serializable(self):
        report = generate_final_report()
        json_str = json.dumps(report, default=str)
        self.assertIsInstance(json_str, str)


class TestReportFiles(unittest.TestCase):
    def test_report_file_creation(self):
        paths = save_final_reports()
        for name, path in paths.items():
            self.assertTrue(os.path.exists(path), f"{name} not created at {path}")

    def test_data_quality_json(self):
        paths = save_final_reports()
        with open(paths["data_quality_report"], "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("quality_score", data)
        self.assertIn("checks", data)

    def test_data_quality_csv(self):
        paths = save_final_reports()
        with open(paths["data_quality_summary"], "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.assertGreater(len(rows), 0)
        for row in rows:
            self.assertIn("check_name", row)
            self.assertIn("status", row)

    def test_operational_report_json(self):
        paths = save_final_reports()
        with open(paths["operational_report"], "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("total_events", data)

    def test_final_report_json(self):
        paths = save_final_reports()
        with open(paths["final_report"], "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("generated_at", data)

    def test_final_report_txt(self):
        paths = save_final_reports()
        with open(paths["final_report_txt"], "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("LOGFLOW FINAL REPORT", content)

    def test_empty_data_behavior(self):
        report = generate_data_quality_report(pd.DataFrame())
        self.assertEqual(report["total_records"], 0)
        self.assertGreaterEqual(report["quality_score"], 0.0)


class TestLoadAnomalyReport(unittest.TestCase):
    def test_load_existing(self):
        report = _load_anomaly_report()
        self.assertIsInstance(report, dict)

    def test_load_missing_file(self):
        import app.reporting as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = "/nonexistent/path"
        try:
            report = _load_anomaly_report()
            self.assertEqual(report["total_records"], 0)
        finally:
            mod.OUTPUT_DIR = orig


if __name__ == "__main__":
    unittest.main()
