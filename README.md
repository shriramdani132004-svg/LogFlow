# LogFlow

Application Log Processing & Anomaly Detection Pipeline

## Problem Statement

Application logs contain critical operational data, but raw logs are unstructured and difficult to analyze at scale. Manual log review fails to detect anomalies in real-time, leading to delayed incident response and missed performance issues.

## Project Objective

LogFlow automates the end-to-end workflow of ingesting, parsing, storing, analyzing, and visualizing application log data. It detects anomalous events using machine learning and rule-based signals, providing operational insights through an interactive dashboard.

## Main Features

- Realistic synthetic log generation with configurable record counts
- Pipe-delimited log format parsing with structured field extraction
- Data validation, cleaning, and duplicate detection
- PostgreSQL storage with idempotent batch loading
- 13 SQL analytics queries for operational insights
- Isolation Forest anomaly detection with explainable rule-based signals
- Comprehensive data quality and operational reporting
- Interactive Streamlit dashboard with filters

## Technology Stack

| Technology | Purpose |
|-----------|---------|
| Python 3.10+ | Core language |
| PostgreSQL 14+ | Database storage and SQL analytics |
| Pandas | Data manipulation and analysis |
| Scikit-learn | Isolation Forest anomaly detection |
| Streamlit | Interactive web dashboard |
| Pytest | Test framework |

## Complete Pipeline Workflow

```
Raw Application Logs
        |
Log Generation / Ingestion
        |
Parsing / Validation
        |
Cleaning / Duplicate Detection
        |
Cleaned Data (CSV)
        |
PostgreSQL Database
        |
SQL Analytics  <-->  Anomaly Detection
        |                    |
Reports / CSV / JSON  <------+
        |
Streamlit Dashboard
```

## Parts 1-10 Status

| Part | Topic | Status |
|------|-------|--------|
| Part 1 | Project Foundation | Complete |
| Part 2 | Log Generation & Ingestion | Complete |
| Part 3 | Log Parsing & Data Cleaning | Complete |
| Part 4 | PostgreSQL Data Pipeline | Complete |
| Part 5 | SQL Analytics | Complete |
| Part 6 | Anomaly Detection | Complete |
| Part 7 | Data Quality Reporting | Complete |
| Part 8 | Streamlit Dashboard | Complete |
| Part 9 | Testing & Documentation | Complete |
| Part 10 | Resume & Interview Preparation | Complete |

## Project Structure

```
LogFlow/
├── app/
│   ├── __init__.py
│   ├── config.py               # Environment and path configuration
│   ├── main.py                 # Application entry point
│   ├── log_generator.py        # Synthetic log generation
│   ├── ingestion.py            # Raw log file reading
│   ├── log_parser.py           # Log line parsing
│   ├── processor.py            # Validation, cleaning, deduplication
│   ├── database.py             # PostgreSQL connection management
│   ├── db_loader.py            # CSV-to-database loading
│   ├── analytics.py            # SQL analytics queries
│   ├── anomaly_detection.py    # ML anomaly detection
│   └── reporting.py            # Report generation
├── dashboard.py                # Streamlit web dashboard
├── run.py                      # CLI entry point
├── sql/
│   ├── schema.sql              # Database schema
│   └── analytics.sql           # Analytics queries
├── tests/
│   ├── __init__.py
│   ├── test_log_generator.py
│   ├── test_ingestion.py
│   ├── test_log_parser.py
│   ├── test_processor.py
│   ├── test_database.py
│   ├── test_db_loader.py
│   ├── test_analytics.py
│   ├── test_anomaly_detection.py
│   ├── test_reporting.py
│   ├── test_dashboard.py
│   └── data/sample_logs/       # Sample datasets for testing
│       ├── valid_logs.txt
│       ├── malformed_logs.txt
│       ├── missing_value_logs.txt
│       ├── duplicate_logs.txt
│       └── anomaly_logs.txt
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   └── testing.md
├── data/
│   ├── input/                  # Generated raw log files
│   └── output/                 # All generated outputs
├── .env                        # Environment variables (not committed)
├── requirements.txt
└── README.md
```

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- pip (Python package manager)

## PostgreSQL Requirements

A running PostgreSQL instance with a user that has CREATE and INSERT permissions. The pipeline creates and manages a `logflow` database.

## Environment Configuration

Create a `.env` file in the project root:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=logflow
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_BATCH_SIZE=500
```

## Installation & Setup

```bash
# Clone repository
git clone <repository-url>
cd LogFlow

# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create PostgreSQL database
createdb -U postgres logflow

# Create .env file with your credentials
```

## CLI Commands

### Log Generation

```bash
python run.py generate              # Generate 100 sample logs (default)
python run.py generate --records 500  # Generate 500 sample logs
```

### Ingestion

```bash
python run.py ingest
```

Reads raw log files from `data/input/` into memory.

### Processing

```bash
python run.py process
```

Parses, validates, cleans, and deduplicates logs. Outputs `cleaned_logs.csv` and `rejected_logs.csv` to `data/output/`.

### Database Initialization

```bash
python run.py db-init
```

Creates the `log_events` table with constraints and indexes.

### Database Loading

```bash
python run.py db-load
```

Loads `cleaned_logs.csv` into PostgreSQL using batch inserts with idempotent ON CONFLICT handling.

### Database Verification

```bash
python run.py db-verify
```

Verifies table existence, row counts, and timestamp ranges.

### Analytics

```bash
python run.py analyze
```

Runs 13 SQL analytics queries. Saves `analytics_report.json` to `data/output/`.

### Anomaly Detection

```bash
python run.py detect
python run.py detect --contamination 0.05
```

Runs Isolation Forest + rule-based detection. Saves `anomalies.csv` and `anomaly_report.json`.

### Reporting

```bash
python run.py report
```

Generates data quality, operational, and final reports.

### Dashboard

```bash
streamlit run dashboard.py
```

Opens interactive dashboard at http://localhost:8501

### Testing

```bash
python -m pytest -q
```

## Expected Output Files

All outputs are saved to `data/output/`:

| File | Description |
|------|-------------|
| `cleaned_logs.csv` | Parsed and cleaned log records |
| `rejected_logs.csv` | Records that failed validation |
| `analytics_report.json` | SQL analytics results |
| `anomalies.csv` | Full scored dataset with anomaly labels |
| `anomaly_report.json` | Anomaly detection summary |
| `data_quality_report.json` | Data quality check results |
| `data_quality_summary.csv` | Quality metrics in CSV format |
| `operational_report.json` | Operational metrics summary |
| `final_report.json` | Combined final report |
| `final_report.txt` | Human-readable final report |

## Sample Datasets

Located in `tests/data/sample_logs/`:

- **valid_logs.txt**: 10 valid log lines covering all 9 event types
- **malformed_logs.txt**: Mix of valid and malformed lines for testing rejection
- **missing_value_logs.txt**: Logs with varying field completeness
- **duplicate_logs.txt**: Logs with intentional duplicate records
- **anomaly_logs.txt**: Logs with patterns designed to trigger anomaly detection (high response times, 5xx errors, auth failures)

These are small, human-readable datasets used for unit testing. They do not replace the realistic 500-record generated workflow.

## Data Quality Behavior

Data quality checks run as part of the reporting stage:

- **Required fields**: timestamp, log_level, event_type must be non-NULL
- **Optional fields**: service, endpoint, method, status, response_time_ms, user_id checked for NULL rates
- **Validity**: HTTP status codes must be 100-599, response times must be non-negative
- **Uniqueness**: No duplicate record IDs
- **Consistency**: Log levels must be valid (DEBUG, INFO, WARN, ERROR)

Quality score is computed as: (passed checks / total checks) * 100

## Anomaly Detection Behavior

- Uses Isolation Forest (unsupervised ML) on engineered features
- Features include: response_time_ms, status, error indicators, time-of-day, service/event type
- Rule-based signals provide explainable context alongside ML predictions
- Each anomaly gets an `anomaly_reason` string combining ML and rule signals
- Deterministic with fixed random_state for reproducibility
- Contamination parameter controls expected anomaly fraction (default: 5%)

## Limitations

- Uses generated/simulated application logs, not real production data
- File-based ingestion (no real-time streaming)
- Local PostgreSQL deployment only
- Limited dataset scale (hundreds to low thousands of records)
- Threshold sensitivity in anomaly detection (95th percentile for high response time)
- Streamlit provides a functional but basic dashboard interface
- Isolation Forest is unsupervised and does not guarantee production-grade accuracy
- No alerting or notification system
- No model monitoring or drift detection

## Future Improvements

- Real-time streaming ingestion (Kafka or similar)
- Cloud-based PostgreSQL deployment
- Better feature engineering for anomaly detection
- Model monitoring and drift detection
- Alerting system for anomaly thresholds
- Richer dashboard with drill-down capabilities
- Distributed processing for large-scale logs
- Authentication and multi-tenancy

## Interview Explanation

LogFlow is an end-to-end log processing pipeline built with Python, PostgreSQL, and scikit-learn. It generates realistic application logs, parses them into structured data using a pipe-delimited format, validates and cleans the records, stores them in PostgreSQL, and runs SQL analytics for operational insights. The anomaly detection stage uses Isolation Forest on engineered features combined with rule-based signals to identify unusual events. Results are presented through a Streamlit dashboard and comprehensive reports. The project demonstrates ETL processing, database management, data quality validation, machine learning, and data visualization.

## Concise Interview Explanation

I built LogFlow, a Python pipeline that processes application logs through parsing, cleaning, PostgreSQL storage, SQL analytics, and Isolation Forest anomaly detection. It includes a Streamlit dashboard for visualization and comprehensive test coverage using pytest.
