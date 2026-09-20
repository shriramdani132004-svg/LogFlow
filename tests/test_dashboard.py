import json
import os
import tempfile
import unittest

import pandas as pd

from app.config import OUTPUT_DIR


def _import_dashboard():
    import importlib
    import sys
    if "dashboard" in sys.modules:
        importlib.reload(sys.modules["dashboard"])
    from dashboard import (
        load_anomalies_csv,
        load_report,
        filter_dataframe,
        get_unique_values,
    )
    return load_anomalies_csv, load_report, filter_dataframe, get_unique_values


class TestDashboardDataLoading(unittest.TestCase):
    def test_load_report_existing(self):
        from dashboard import load_report
        report = load_report("anomaly_report.json")
        self.assertIsInstance(report, dict)

    def test_load_report_missing(self):
        from dashboard import load_report
        report = load_report("nonexistent_file.json")
        self.assertEqual(report, {})

    def test_load_anomalies_csv_existing(self):
        from dashboard import load_anomalies_csv
        df = load_anomalies_csv()
        self.assertIsInstance(df, pd.DataFrame)

    def test_load_anomalies_csv_missing(self):
        import dashboard as mod
        orig = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = "/nonexistent/path"
        try:
            from dashboard import load_anomalies_csv
            df = load_anomalies_csv()
            self.assertTrue(df.empty)
        finally:
            mod.OUTPUT_DIR = orig


class TestDashboardFiltering(unittest.TestCase):
    def _make_df(self):
        return pd.DataFrame({
            "id": [1, 2, 3, 4],
            "timestamp": ["2026-09-20 10:00:00", "2026-09-20 10:01:00",
                          "2026-09-20 10:02:00", "2026-09-20 10:03:00"],
            "log_level": ["INFO", "ERROR", "INFO", "WARN"],
            "event_type": ["API_REQUEST", "API_REQUEST", "USER_LOGIN", "API_REQUEST"],
            "service": ["auth", "auth", "payments", "auth"],
            "endpoint": ["/api/login", "/api/login", None, "/api/pay"],
            "method": ["POST", "POST", None, "POST"],
            "status": [200, 500, None, 400],
            "response_time_ms": [100, 2000, None, 80],
            "user_id": ["U100", "U101", None, "U102"],
            "is_anomaly": [False, True, False, False],
        })

    def test_service_filter(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, service="auth")
        self.assertEqual(len(result), 3)

    def test_log_level_filter(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, log_level="ERROR")
        self.assertEqual(len(result), 1)

    def test_event_type_filter(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, event_type="USER_LOGIN")
        self.assertEqual(len(result), 1)

    def test_anomaly_only_filter(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, anomaly_only=True)
        self.assertEqual(len(result), 1)
        self.assertTrue(result["is_anomaly"].all())

    def test_response_time_filter(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, min_response_time=1000)
        self.assertEqual(len(result), 1)

    def test_empty_result_filtering(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, service="nonexistent")
        self.assertTrue(result.empty)

    def test_null_safe_rendering(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df, service="payments")
        self.assertEqual(len(result), 1)
        self.assertTrue(pd.isna(result.iloc[0]["endpoint"]))

    def test_no_filters(self):
        df = self._make_df()
        from dashboard import filter_dataframe
        result = filter_dataframe(df)
        self.assertEqual(len(result), 4)

    def test_get_unique_values(self):
        df = self._make_df()
        from dashboard import get_unique_values
        vals = get_unique_values(df, "service")
        self.assertIn("All", vals)
        self.assertIn("auth", vals)
        self.assertIn("payments", vals)

    def test_get_unique_values_missing_column(self):
        df = self._make_df()
        from dashboard import get_unique_values
        vals = get_unique_values(df, "nonexistent")
        self.assertEqual(vals, ["All"])

    def test_get_unique_values_empty_df(self):
        df = pd.DataFrame()
        from dashboard import get_unique_values
        vals = get_unique_values(df, "service")
        self.assertEqual(vals, ["All"])


if __name__ == "__main__":
    unittest.main()
