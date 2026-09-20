import json
import os

import pandas as pd
import streamlit as st

from app.config import OUTPUT_DIR
from app.database import close_connection, get_connection
from app.analytics import run_all_analytics


def load_anomalies_csv():
    path = os.path.join(OUTPUT_DIR, "anomalies.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def load_report(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_log_data_from_db():
    try:
        conn = get_connection()
        df = pd.read_sql_query(
            """SELECT id, timestamp, log_level, event_type, service,
                      endpoint, method, status, response_time_ms, user_id
               FROM log_events ORDER BY id LIMIT 500""",
            conn,
        )
        close_connection(conn)
        return df
    except Exception:
        return pd.DataFrame()


def filter_dataframe(df, service=None, log_level=None, event_type=None,
                     anomaly_only=False, min_response_time=None):
    if df.empty:
        return df

    filtered = df.copy()

    if service and service != "All":
        filtered = filtered[filtered["service"] == service]

    if log_level and log_level != "All":
        filtered = filtered[filtered["log_level"] == log_level]

    if event_type and event_type != "All":
        filtered = filtered[filtered["event_type"] == event_type]

    if anomaly_only and "is_anomaly" in filtered.columns:
        filtered = filtered[filtered["is_anomaly"] == True]

    if min_response_time is not None and "response_time_ms" in filtered.columns:
        filtered = filtered[filtered["response_time_ms"] >= min_response_time]

    return filtered


def get_unique_values(df, column):
    if df.empty or column not in df.columns:
        return ["All"]
    vals = df[column].dropna().unique().tolist()
    return ["All"] + sorted(vals)


def render_kpi_cards(dq_report, op_report):
    col1, col2, col3, col4 = st.columns(4)
    total = op_report.get("total_events", 0)
    errors = op_report.get("error_count", 0)
    warnings = op_report.get("warning_count", 0)
    avg_rt = op_report.get("average_response_time_ms", "N/A")

    with col1:
        st.metric("Total Events", total)
    with col2:
        st.metric("Errors", errors)
    with col3:
        st.metric("Warnings", warnings)
    with col4:
        st.metric("Avg Response Time", f"{avg_rt} ms" if avg_rt != "N/A" else "N/A")

    col5, col6, col7, col8 = st.columns(4)
    five_xx = op_report.get("anomaly_count", 0)
    anomaly_count = op_report.get("anomaly_count", 0)
    anomaly_rate = op_report.get("anomaly_rate", 0.0)
    quality_score = dq_report.get("quality_score", 0.0)

    with col5:
        st.metric("5xx Responses", op_report.get("server_error_count", 0))
    with col6:
        st.metric("Anomalies", anomaly_count)
    with col7:
        st.metric("Anomaly Rate", f"{anomaly_rate}%")
    with col8:
        st.metric("Quality Score", f"{quality_score}%")


def render_overview_charts(op_report):
    st.subheader("Overview")

    log_dist = op_report.get("log_level_distribution", [])
    if log_dist:
        st.markdown("**Log Level Distribution**")
        chart_data = pd.DataFrame(log_dist)
        st.bar_chart(chart_data.set_index("log_level")["event_count"])

    evt_dist = op_report.get("event_type_distribution", [])
    if evt_dist:
        st.markdown("**Event Type Distribution**")
        chart_data = pd.DataFrame(evt_dist)
        st.bar_chart(chart_data.set_index("event_type")["event_count"])

    sp = op_report.get("service_performance", [])
    if sp:
        st.markdown("**Service Distribution**")
        chart_data = pd.DataFrame(sp)
        st.bar_chart(chart_data.set_index("service")["total_count"])


def render_response_time_section(op_report):
    st.subheader("Response Time")
    avg_rt = op_report.get("average_response_time_ms", "N/A")
    max_rt = op_report.get("max_response_time_ms", "N/A")
    st.write(f"Average: {avg_rt} ms | Maximum: {max_rt} ms")

    slow = op_report.get("slowest_endpoints", [])
    if slow:
        st.markdown("**Slowest Endpoints**")
        st.dataframe(pd.DataFrame(slow))


def render_anomaly_section(anomalies_df, op_report):
    st.subheader("Anomaly Detection")

    ac = op_report.get("anomaly_count", 0)
    ar = op_report.get("anomaly_rate", 0.0)
    st.write(f"Anomalies: {ac} | Rate: {ar}%")

    a_by_svc = op_report.get("anomalies_by_service", {})
    if a_by_svc:
        st.markdown("**Anomalies by Service**")
        st.bar_chart(pd.Series(a_by_svc))

    a_by_evt = op_report.get("anomalies_by_event_type", {})
    if a_by_evt:
        st.markdown("**Anomalies by Event Type**")
        st.bar_chart(pd.Series(a_by_evt))

    if not anomalies_df.empty:
        st.markdown("**Anomalous Events**")
        display_cols = ["timestamp", "service", "event_type", "endpoint",
                        "status", "response_time_ms", "anomaly_score", "anomaly_reason"]
        available = [c for c in display_cols if c in anomalies_df.columns]
        st.dataframe(anomalies_df[anomalies_df.get("is_anomaly", False) == True][available])


def render_data_quality_section(dq_report):
    st.subheader("Data Quality")
    st.write(f"Quality Score: {dq_report.get('quality_score', 0)}%")
    st.write(f"Passed: {dq_report.get('quality_checks_passed', 0)} | "
             f"Failed: {dq_report.get('quality_checks_failed', 0)} | "
             f"Warned: {dq_report.get('quality_checks_warned', 0)}")

    checks = dq_report.get("checks", [])
    if checks:
        st.dataframe(pd.DataFrame(checks))


def render_recent_logs(df):
    st.subheader("Recent Logs")
    if df.empty:
        st.info("No log data available.")
        return
    st.dataframe(df.tail(100))


def main():
    st.set_page_config(page_title="LogFlow Dashboard", layout="wide")
    st.title("LogFlow — Application Log Intelligence Dashboard")
    st.caption("Application log processing, operational analytics, and anomaly detection")

    # Load data
    dq_report = load_report("data_quality_report.json")
    op_report = load_report("operational_report.json")
    anomalies_df = load_anomalies_csv()
    logs_df = load_log_data_from_db()

    # Filters
    st.sidebar.header("Filters")
    service_filter = st.sidebar.selectbox("Service", get_unique_values(logs_df, "service"))
    level_filter = st.sidebar.selectbox("Log Level", get_unique_values(logs_df, "log_level"))
    event_filter = st.sidebar.selectbox("Event Type", get_unique_values(logs_df, "event_type"))
    anomaly_only = st.sidebar.checkbox("Anomaly Only", value=False)
    min_rt = st.sidebar.number_input("Min Response Time (ms)", min_value=0, value=0)

    # Apply filters to logs
    filtered_logs = filter_dataframe(
        logs_df, service=service_filter, log_level=level_filter,
        event_type=event_filter, min_response_time=min_rt if min_rt > 0 else None,
    )

    # Apply filters to anomalies
    filtered_anomalies = filter_dataframe(
        anomalies_df, service=service_filter, log_level=level_filter,
        event_type=event_filter, anomaly_only=True,
    )

    # KPI Cards
    render_kpi_cards(dq_report, op_report)

    # Overview
    render_overview_charts(op_report)

    # Response Time
    render_response_time_section(op_report)

    # Anomalies
    render_anomaly_section(anomalies_df, op_report)

    # Data Quality
    render_data_quality_section(dq_report)

    # Recent Logs
    render_recent_logs(filtered_logs)


if __name__ == "__main__":
    main()
