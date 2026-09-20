import json
import logging
from datetime import datetime, date

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.config import OUTPUT_DIR, RANDOM_SEED
from app.database import close_connection, get_connection

logger = logging.getLogger(__name__)

OUTPUT_COLS = [
    "id", "timestamp", "log_level", "event_type", "service", "endpoint",
    "method", "status", "response_time_ms", "user_id",
    "anomaly_score", "ml_prediction", "is_anomaly",
    "high_response_time", "server_error", "auth_failure",
    "database_error", "error_log", "anomaly_reason",
]

NUMERIC_COLS = ["response_time_ms", "status", "is_error", "is_warning",
                "is_auth_failure", "is_database_error", "hour", "day_of_week", "minute_of_hour"]
CATEGORICAL_COLS = ["log_level", "event_type", "service"]


def load_log_data():
    conn = None
    try:
        conn = get_connection()
        df = pd.read_sql_query(
            """SELECT id, timestamp, log_level, event_type, service,
                      endpoint, method, status, response_time_ms, user_id
               FROM log_events ORDER BY id""",
            conn,
        )
        return df
    except Exception as e:
        logger.error("Failed to load log data: %s", e)
        raise
    finally:
        close_connection(conn)


def prepare_features(df):
    if df.empty:
        return df, None

    work = df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")

    work["hour"] = work["timestamp"].dt.hour.fillna(0).astype(int)
    work["day_of_week"] = work["timestamp"].dt.dayofweek.fillna(0).astype(int)
    work["minute_of_hour"] = work["timestamp"].dt.minute.fillna(0).astype(int)

    work["is_error"] = (work["log_level"] == "ERROR").astype(int)
    work["is_warning"] = (work["log_level"] == "WARN").astype(int)
    work["is_auth_failure"] = (work["event_type"] == "AUTH_FAILURE").astype(int)
    work["is_database_error"] = (work["event_type"] == "DATABASE_ERROR").astype(int)

    work["status"] = work["status"].astype("Int64").astype(float)
    work["response_time_ms"] = work["response_time_ms"].astype("Int64").astype(float)
    work["service"] = work["service"].fillna("UNKNOWN")
    work["log_level"] = work["log_level"].fillna("UNKNOWN")
    work["event_type"] = work["event_type"].fillna("UNKNOWN")

    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
    ])

    categorical_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_COLS),
            ("cat", categorical_transformer, CATEGORICAL_COLS),
        ],
        remainder="drop",
    )

    return work, preprocessor


def detect_anomalies(df, preprocessor, contamination=0.05, random_state=RANDOM_SEED):
    if df.empty or preprocessor is None:
        df = df.copy()
        df["anomaly_score"] = np.nan
        df["ml_prediction"] = np.nan
        df["is_anomaly"] = False
        return df

    feature_cols = NUMERIC_COLS + CATEGORICAL_COLS
    X = df[feature_cols].copy()

    X_processed = preprocessor.fit_transform(X)

    min_samples = max(2, int(1.0 / contamination) + 1) if contamination > 0 else 3
    if X_processed.shape[0] < min_samples:
        df = df.copy()
        df["anomaly_score"] = np.nan
        df["ml_prediction"] = np.nan
        df["is_anomaly"] = False
        return df

    clf = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    predictions = clf.fit_predict(X_processed)
    scores = clf.decision_function(X_processed)

    df = df.copy()
    df["anomaly_score"] = scores
    df["ml_prediction"] = predictions
    df["is_anomaly"] = predictions == -1

    return df


def calculate_rule_signals(df):
    work = df.copy()

    valid_rt = work["response_time_ms"].dropna()
    if len(valid_rt) > 0:
        p95 = np.percentile(valid_rt, 95)
        work["high_response_time"] = work["response_time_ms"].fillna(0) > p95
    else:
        work["high_response_time"] = False

    work["server_error"] = work["status"].fillna(0).astype(int).between(500, 599)
    work["auth_failure"] = work["event_type"].fillna("") == "AUTH_FAILURE"
    work["database_error"] = work["event_type"].fillna("") == "DATABASE_ERROR"
    work["error_log"] = work["log_level"] == "ERROR"

    return work


def build_anomaly_reason(row):
    reasons = []
    if row.get("ml_prediction") == -1:
        reasons.append("Isolation Forest anomaly")
    if row.get("high_response_time"):
        reasons.append("High response time")
    if row.get("server_error"):
        reasons.append("5xx server error")
    if row.get("auth_failure"):
        reasons.append("Authentication failure")
    if row.get("database_error"):
        reasons.append("Database error")
    if row.get("error_log"):
        reasons.append("Error log level")
    return " + ".join(reasons) if reasons else ""


def generate_anomaly_report(df):
    total = len(df)
    anomalies = df["is_anomaly"].sum()

    report = {
        "total_records": int(total),
        "anomaly_count": int(anomalies),
        "anomaly_rate": round(float(anomalies / total * 100), 2) if total > 0 else 0.0,
        "normal_count": int(total - anomalies),
        "high_response_time_count": int(df["high_response_time"].sum()),
        "server_error_count": int(df["server_error"].sum()),
        "auth_failure_count": int(df["auth_failure"].sum()),
        "database_error_count": int(df["database_error"].sum()),
        "error_log_count": int(df["error_log"].sum()),
    }

    anomaly_df = df[df["is_anomaly"]]

    if not anomaly_df.empty:
        report["anomalies_by_service"] = (
            anomaly_df.groupby("service").size()
            .sort_values(ascending=False).head(10).to_dict()
        )
        report["anomalies_by_event_type"] = (
            anomaly_df.groupby("event_type").size()
            .sort_values(ascending=False).head(10).to_dict()
        )
        report["anomalies_by_log_level"] = (
            anomaly_df.groupby("log_level").size()
            .sort_values(ascending=False).to_dict()
        )
        report["anomalies_by_status"] = (
            anomaly_df.groupby("status").size()
            .sort_values(ascending=False).head(10).to_dict()
        )
        ep_df = anomaly_df[anomaly_df["endpoint"].notna()]
        if not ep_df.empty:
            report["top_anomalous_endpoints"] = (
                ep_df.groupby("endpoint").size()
                .sort_values(ascending=False).head(10).to_dict()
            )
        else:
            report["top_anomalous_endpoints"] = {}
    else:
        report["anomalies_by_service"] = {}
        report["anomalies_by_event_type"] = {}
        report["anomalies_by_log_level"] = {}
        report["anomalies_by_status"] = {}
        report["top_anomalous_endpoints"] = {}

    return report


def _json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def save_anomaly_results(df, report, output_dir=OUTPUT_DIR):
    import os
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, "anomalies.csv")
    json_path = os.path.join(output_dir, "anomaly_report.json")

    out_df = df[OUTPUT_COLS].copy()
    out_df["is_anomaly"] = out_df["is_anomaly"].astype(bool)
    out_df["timestamp"] = out_df["timestamp"].astype(str)
    out_df.to_csv(csv_path, index=False)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=_json_serializer)

    return csv_path, json_path


def print_anomaly_summary(report):
    print("## Anomaly Detection")
    print()
    print(f"  Total records       : {report['total_records']}")
    print(f"  Anomalies detected  : {report['anomaly_count']}")
    print(f"  Anomaly rate        : {report['anomaly_rate']}%")

    print()
    print("## Signals")
    print(f"  High response time  : {report['high_response_time_count']}")
    print(f"  5xx errors          : {report['server_error_count']}")
    print(f"  Auth failures       : {report['auth_failure_count']}")
    print(f"  Database errors     : {report['database_error_count']}")
    print(f"  Error logs          : {report['error_log_count']}")

    if report.get("anomalies_by_service"):
        print()
        print("## Top anomalous services")
        for svc, cnt in list(report["anomalies_by_service"].items())[:5]:
            print(f"  {_fmt(svc, 20)}: {cnt}")

    if report.get("anomalies_by_event_type"):
        print()
        print("## Top anomalous event types")
        for evt, cnt in list(report["anomalies_by_event_type"].items())[:5]:
            print(f"  {_fmt(evt, 25)}: {cnt}")

    if report.get("top_anomalous_endpoints"):
        print()
        print("## Top anomalous endpoints")
        for ep, cnt in list(report["top_anomalous_endpoints"].items())[:5]:
            print(f"  {_fmt(ep, 35)}: {cnt}")


_NA = "N/A"


def _fmt(value, width=None):
    if value is None:
        if width is not None:
            return _NA.ljust(width)
        return _NA
    if width is not None:
        return f"{value:<{width}}"
    return str(value)


def run_anomaly_detection(contamination=0.05):
    df = load_log_data()

    work, preprocessor = prepare_features(df)
    work = detect_anomalies(work, preprocessor, contamination=contamination)
    work = calculate_rule_signals(work)
    work["anomaly_reason"] = work.apply(build_anomaly_reason, axis=1)

    report = generate_anomaly_report(work)
    csv_path, json_path = save_anomaly_results(work, report)
    print_anomaly_summary(report)
    print(f"\nCSV saved  : {csv_path}")
    print(f"JSON saved : {json_path}")

    return work, report
