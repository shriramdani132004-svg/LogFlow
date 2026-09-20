import os
import sys

from app.main import main as app_main
from app.log_generator import generate_logs
from app.ingestion import ingest_logs, print_ingestion_stats
from app.processor import process_logs, print_processing_stats
from app.db_loader import (
    init_schema,
    load_csv_to_db,
    print_load_stats,
    print_verify_stats,
    verify_database,
)
from app.analytics import run_all_analytics, save_report, print_report


def parse_contamination(args):
    for i, arg in enumerate(args):
        if arg == "--contamination" and i + 1 < len(args):
            return float(args[i + 1])
    return 0.05


def parse_record_count(args):
    for i, arg in enumerate(args):
        if arg == "--records" and i + 1 < len(args):
            return int(args[i + 1])
    return None


def main():
    args = sys.argv[1:]

    if not args:
        app_main()
        return

    command = args[0].lower()

    if command == "generate":
        record_count = parse_record_count(args)
        count, output_file = generate_logs(record_count=record_count)
        print(f"Generated {count} log records -> {output_file}")

    elif command == "ingest":
        records, stats = ingest_logs()
        print_ingestion_stats(stats)

    elif command == "process":
        df, stats, cleaned_path, rejected_path = process_logs()
        print_processing_stats(stats)
        print(f"\nCleaned output : {cleaned_path}")
        print(f"Rejected output: {rejected_path}")

    elif command == "db-init":
        try:
            init_schema()
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif command == "db-load":
        try:
            stats = load_csv_to_db()
            print_load_stats(stats)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif command == "db-verify":
        try:
            info = verify_database()
            print_verify_stats(info)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif command == "analyze":
        try:
            from app.config import OUTPUT_DIR
            data = run_all_analytics()
            print_report(data)
            report_path = os.path.join(OUTPUT_DIR, "analytics_report.json")
            save_report(data, report_path)
            print(f"\nReport saved: {report_path}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif command == "detect":
        try:
            contamination = parse_contamination(args)
            from app.anomaly_detection import run_anomaly_detection
            run_anomaly_detection(contamination=contamination)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        print("Usage:")
        print("  python run.py              - Start LogFlow foundation")
        print("  python run.py generate     - Generate sample logs")
        print("  python run.py generate --records N")
        print("  python run.py ingest       - Ingest raw logs")
        print("  python run.py process      - Parse, validate, and clean logs")
        print("  python run.py db-init      - Initialize database schema")
        print("  python run.py db-load      - Load cleaned CSV into PostgreSQL")
        print("  python run.py db-verify    - Verify database contents")
        print("  python run.py analyze      - Run SQL analytics on log data")
        print("  python run.py detect       - Run anomaly detection")
        print("  python run.py detect --contamination 0.05")
        sys.exit(1)


if __name__ == "__main__":
    main()
