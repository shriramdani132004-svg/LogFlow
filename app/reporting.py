import csv
import json
import logging
import os
from datetime import datetime, date

import numpy as np
import pandas as pd

from app.config import OUTPUT_DIR, CLEANED_OUTPUT
from app.database import close_connection, get_connection
from app.analytics import run_all_analytics
from app.anomaly_detection import load_log_data, _json_serializer

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["timestamp", "log_level", "event_type"]
OPTIONAL_FIELDS = ["service", "endpoint", "method", "status", "response_time_ms", "user_id"]


def generate_data_quality_report(df=None):
    if df is None:
        df = _load_from_db()

    if df.empty:
        return {
            "total_records": 0,
            "earliest_timestamp": None,
            "latest_timestamp": None,
            "quality_checks_passed": 0,
            "quality_checks_failed": 0,
            "quality_checks_warned": 0,
            "quality_score": 0.0,
            "checks": [],
        }

    total = len(df)
    checks = []

    # Completeness: required fields
    for field in REQUIRED_FIELDS:
        null_count = int(df[field].isna().sum())
        null_pct = round(null_count / total * 100, 2) if total > 0 else 0.0
        status = "PASS" if null_count == 0 else "FAIL"
        checks.append({
            "check_name": f"{field}_completeness",
            "category": "completeness",
            "status": status,
            "value": null_count,
            "threshold": 0,
            "message": f"{field}: {null_count} NULL values ({null_pct}%)",
        })

    # Completeness: optional fields
    for field in OPTIONAL_FIELDS:
        null_count = int(df[field].isna().sum())
        null_pct = round(null_count / total * 100, 2) if total > 0 else 0.0
        status = "PASS" if null_pct < 50 else "WARN" if null_pct < 100 else "FAIL"
        checks.append({
            "check_name": f"{field}_completeness",
            "category": "completeness",
            "status": status,
            "value": null_count,
            "threshold": 0,
            "message": f"{field}: {null_count} NULL values ({null_pct}%)",
        })

    # Validity: negative response times
    rt = df["response_time_ms"].dropna()
    neg_rt = int((rt < 0).sum())
    checks.append({
        "check_name": "negative_response_times",
        "category": "validity",
        "status": "PASS" if neg_rt == 0 else "FAIL",
        "value": neg_rt,
        "threshold": 0,
        "message": f"{neg_rt} negative response times",
    })

    # Validity: invalid HTTP statuses
    st = df["status"].dropna()
    invalid_status = int(((st < 100) | (st > 599)).sum())
    checks.append({
        "check_name": "invalid_http_status",
        "category": "validity",
        "status": "PASS" if invalid_status == 0 else "FAIL",
        "value": invalid_status,
        "threshold": 0,
        "message": f"{invalid_status} invalid HTTP statuses",
    })

    # Uniqueness: duplicate IDs
    dup_ids = int(df["id"].duplicated().sum())
    checks.append({
        "check_name": "duplicate_ids",
        "category": "uniqueness",
        "status": "PASS" if dup_ids == 0 else "FAIL",
        "value": dup_ids,
        "threshold": 0,
        "message": f"{dup_ids} duplicate record IDs",
    })

    # Consistency: valid log levels
    valid_levels = {"DEBUG", "INFO", "WARN", "ERROR"}
    invalid_levels = int(~df["log_level"].dropna().isin(valid_levels).sum())
    checks.append({
        "check_name": "valid_log_levels",
        "category": "consistency",
        "status": "PASS" if invalid_levels == 0 else "FAIL",
        "value": invalid_levels,
        "threshold": 0,
        "message": f"{invalid_levels} invalid log levels",
    })

    # Null counts by column
    for col in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        nc = int(df[col].isna().sum())
        checks.append({
            "check_name": f"{col}_null_count",
            "category": "completeness",
            "status": "PASS" if nc == 0 else "WARN",
            "value": nc,
            "threshold": 0,
            "message": f"{col}: {nc} NULLs",
        })

    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = sum(1 for c in checks if c["status"] == "FAIL")
    warns = sum(1 for c in checks if c["status"] == "WARN")
    total_checks = len(checks)
    quality_score = round(passed / total_checks * 100, 1) if total_checks > 0 else 0.0

    earliest = None
    latest = None
    if not df.empty:
        try:
            earliest = str(df["timestamp"].min())
            latest = str(df["timestamp"].max())
        except Exception:
            pass

    report = {
        "total_records": total,
        "earliest_timestamp": earliest,
        "latest_timestamp": latest,
        "quality_checks_passed": passed,
        "quality_checks_failed": failed,
        "quality_checks_warned": warns,
        "quality_score": quality_score,
        "checks": checks,
    }

    return report


def generate_operational_report(analytics=None, anomaly_report=None):
    if analytics is None:
        analytics = run_all_analytics()

    if anomaly_report is None:
        anomaly_report = _load_anomaly_report()

    es = analytics["error_summary"]
    rt = analytics["response_time_summary"]

    report = {
        "total_events": analytics["overall_summary"]["total_records"],
        "log_level_distribution": analytics["log_level_distribution"],
        "event_type_distribution": analytics["event_type_distribution"],
        "error_count": es["total_errors"],
        "warning_count": es["total_warnings"],
        "auth_failure_count": es["auth_failures"],
        "database_error_count": es["database_errors"],
        "average_response_time_ms": rt["avg_response_time_ms"],
        "max_response_time_ms": rt["max_response_time_ms"],
        "slowest_endpoints": analytics["slowest_endpoints"],
        "busiest_endpoints": analytics["most_used_endpoints"],
        "service_performance": analytics["service_performance"],
        "anomaly_count": anomaly_report.get("anomaly_count", 0),
        "anomaly_rate": anomaly_report.get("anomaly_rate", 0.0),
        "anomalies_by_service": anomaly_report.get("anomalies_by_service", {}),
        "anomalies_by_event_type": anomaly_report.get("anomalies_by_event_type", {}),
        "anomalies_by_status": anomaly_report.get("anomalies_by_status", {}),
        "top_anomalous_endpoints": anomaly_report.get("top_anomalous_endpoints", {}),
    }

    return report


def generate_top_findings(operational):
    findings = []
    total = operational.get("total_events", 0)

    # Highest-volume service
    sp = operational.get("service_performance", [])
    if sp:
        top_svc = sp[0]
        findings.append(
            f"Highest-volume service: {top_svc['service']} with {top_svc['total_count']} events"
        )

    # Highest error-count service
    error_svcs = [s for s in sp if s.get("error_count", 0) > 0]
    if error_svcs:
        worst = max(error_svcs, key=lambda x: x["error_count"])
        findings.append(
            f"Highest error-count service: {worst['service']} with {worst['error_count']} errors"
        )

    # Slowest endpoint
    slow = operational.get("slowest_endpoints", [])
    if slow:
        findings.append(
            f"Slowest endpoint: {slow[0]['endpoint']} (avg {slow[0]['avg_response_time_ms']} ms)"
        )

    # Anomaly count
    ac = operational.get("anomaly_count", 0)
    ar = operational.get("anomaly_rate", 0.0)
    if ac > 0:
        findings.append(f"Detected {ac} anomalies ({ar}% of total events)")

    # Highest anomaly event type
    aet = operational.get("anomalies_by_event_type", {})
    if aet:
        top_evt = max(aet, key=aet.get)
        findings.append(f"Highest anomaly-producing event type: {top_evt} ({aet[top_evt]} anomalies)")

    # 5xx count
    five_xx = sum(
        r.get("event_count", 0)
        for r in operational.get("log_level_distribution", [])
    )
    sc = operational.get("log_level_distribution", [])
    if not findings:
        findings.append("No significant anomalies detected in current dataset")

    return findings


def generate_final_report():
    analytics = run_all_analytics()
    anomaly_report = _load_anomaly_report()
    operational = generate_operational_report(analytics, anomaly_report)
    dq_report = generate_data_quality_report()
    findings = generate_top_findings(operational)

    return {
        "generated_at": datetime.now().isoformat(),
        "dataset": {
            "total_records": analytics["overall_summary"]["total_records"],
            "earliest_timestamp": str(analytics["overall_summary"]["earliest_timestamp"]),
            "latest_timestamp": str(analytics["overall_summary"]["latest_timestamp"]),
        },
        "data_quality": dq_report,
        "operational_metrics": operational,
        "anomaly_detection": anomaly_report,
        "top_findings": findings,
    }


def save_final_reports():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    dq_report = generate_data_quality_report()
    operational = generate_operational_report()
    final_report = generate_final_report()
    findings = generate_top_findings(operational)

    # Data quality JSON
    dq_json_path = os.path.join(OUTPUT_DIR, "data_quality_report.json")
    with open(dq_json_path, "w", encoding="utf-8") as f:
        json.dump(dq_report, f, indent=2, default=_json_serializer)

    # Data quality CSV
    dq_csv_path = os.path.join(OUTPUT_DIR, "data_quality_summary.csv")
    with open(dq_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["check_name", "category", "status", "value", "threshold", "message"])
        writer.writeheader()
        writer.writerows(dq_report["checks"])

    # Operational JSON
    op_json_path = os.path.join(OUTPUT_DIR, "operational_report.json")
    with open(op_json_path, "w", encoding="utf-8") as f:
        json.dump(operational, f, indent=2, default=_json_serializer)

    # Final JSON
    final_json_path = os.path.join(OUTPUT_DIR, "final_report.json")
    with open(final_json_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, default=_json_serializer)

    # Final TXT
    txt_path = os.path.join(OUTPUT_DIR, "final_report.txt")
    _write_text_report(final_report, operational, dq_report, findings, txt_path)

    return {
        "data_quality_report": dq_json_path,
        "data_quality_summary": dq_csv_path,
        "operational_report": op_json_path,
        "final_report": final_json_path,
        "final_report_txt": txt_path,
    }


def _write_text_report(final, operational, dq, findings, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# LOGFLOW FINAL REPORT\n\n")
        f.write(f"Generated: {final['generated_at']}\n\n")

        f.write("## Dataset\n\n")
        f.write(f"Total records: {final['dataset']['total_records']}\n")
        f.write(f"Time range: {final['dataset']['earliest_timestamp']} to {final['dataset']['latest_timestamp']}\n\n")

        f.write("## Data Quality\n\n")
        f.write(f"Quality score: {dq['quality_score']}%\n")
        f.write(f"Checks passed: {dq['quality_checks_passed']}\n")
        f.write(f"Checks failed: {dq['quality_checks_failed']}\n\n")

        f.write("## Operational Summary\n\n")
        f.write(f"Errors: {operational.get('error_count', 0)}\n")
        f.write(f"Warnings: {operational.get('warning_count', 0)}\n")
        f.write(f"Average response time: {operational.get('average_response_time_ms', 'N/A')} ms\n")
        f.write(f"5xx responses: {sum(r.get('event_count', 0) for r in operational.get('log_level_distribution', []))}\n\n")

        f.write("## Anomaly Detection\n\n")
        f.write(f"Anomalies: {operational.get('anomaly_count', 0)}\n")
        f.write(f"Anomaly rate: {operational.get('anomaly_rate', 0.0)}%\n\n")

        f.write("## Top Findings\n\n")
        for i, finding in enumerate(findings, 1):
            f.write(f"{i}. {finding}\n")
        f.write("\n")


def print_final_summary(final_report, dq_report, operational, paths):
    print("## Final LogFlow Report")
    print()
    print(f"  Records        : {final_report['dataset']['total_records']}")
    print(f"  Quality Score  : {dq_report['quality_score']}%")
    print(f"  Errors         : {operational.get('error_count', 0)}")
    print(f"  Anomalies      : {operational.get('anomaly_count', 0)} ({operational.get('anomaly_rate', 0.0)}%)")
    print()
    print("  Reports saved:")
    for name, path in paths.items():
        print(f"    {name}: {path}")


def _load_from_db():
    try:
        return load_log_data()
    except Exception:
        return pd.DataFrame(columns=["id", "timestamp", "log_level", "event_type",
                                      "service", "endpoint", "method", "status",
                                      "response_time_ms", "user_id"])


def _load_anomaly_report():
    path = os.path.join(OUTPUT_DIR, "anomaly_report.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "total_records": 0, "anomaly_count": 0, "anomaly_rate": 0.0,
        "normal_count": 0, "high_response_time_count": 0,
        "server_error_count": 0, "auth_failure_count": 0,
        "database_error_count": 0, "error_log_count": 0,
        "anomalies_by_service": {}, "anomalies_by_event_type": {},
        "anomalies_by_log_level": {}, "anomalies_by_status": {},
        "top_anomalous_endpoints": {},
    }


def run_reporting():
    paths = save_final_reports()

    final_report = json.loads(open(paths["final_report"], "r", encoding="utf-8").read())
    dq_report = json.loads(open(paths["data_quality_report"], "r", encoding="utf-8").read())
    op_report = json.loads(open(paths["operational_report"], "r", encoding="utf-8").read())

    print_final_summary(final_report, dq_report, op_report, paths)
    return paths
