import os

from app.config import INPUT_DIR, RAW_LOG_FILE


def ingest_logs(input_file=None):
    if input_file is None:
        input_file = RAW_LOG_FILE

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(stripped)

    stats = {
        "input_file": input_file,
        "total_lines_read": len(records),
        "empty_lines_skipped": 0,
    }

    return records, stats


def print_ingestion_stats(stats):
    print(f"Ingestion complete:")
    print(f"  Input file       : {stats['input_file']}")
    print(f"  Records read     : {stats['total_lines_read']}")
    print(f"  Empty lines      : {stats['empty_lines_skipped']}")
