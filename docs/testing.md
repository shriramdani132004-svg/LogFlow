# LogFlow Testing Guide

## Test Framework

LogFlow uses Python's built-in `unittest` framework with `pytest` as the test runner.

## Running Tests

### Run all tests

```bash
python -m pytest -q
```

### Run specific test files

```bash
python -m pytest tests/test_log_parser.py -v
python -m pytest tests/test_processor.py -v
python -m pytest tests/test_anomaly_detection.py -v
python -m pytest tests/test_db_loader.py -v
python -m pytest tests/test_analytics.py -v
python -m pytest tests/test_reporting.py -v
python -m pytest tests/test_dashboard.py -v
```

### Run specific test classes

```bash
python -m pytest tests/test_log_parser.py::TestValidLogLineParsing -v
python -m pytest tests/test_processor.py::TestValidation -v
```

## Test Coverage

### Log Parser Tests (`test_log_parser.py`)

- Valid log line parsing (all 9 event types)
- Timestamp extraction and validation
- All log levels (DEBUG, INFO, WARN, ERROR)
- All event types (API_REQUEST, USER_LOGIN, USER_LOGOUT, DATABASE_QUERY, DATABASE_ERROR, AUTH_FAILURE, CACHE_ACCESS, SERVICE_START, SERVICE_STOP)
- Service and endpoint extraction
- Malformed record rejection
- Missing field handling
- Field pattern extraction
- Batch parsing (parse_logs)

### Processor Tests (`test_processor.py`)

- Record validation (required fields, value ranges)
- Status code boundary values (100, 599)
- Response time validation (negative, zero, non-integer)
- Optional service events (USER_LOGIN, AUTH_FAILURE, etc.)
- DataFrame construction
- Duplicate detection
- Timestamp formatting
- Full pipeline processing
- Deterministic output
- Empty input handling
- Mixed valid/invalid input

### Anomaly Detection Tests (`test_anomaly_detection.py`)

- Feature preparation (numerical, time, binary indicators)
- NULL handling in features
- Isolation Forest execution
- Deterministic output with fixed seed
- Configurable contamination
- Rule-based signals (high response time, 5xx, auth failure, database error, error log)
- Anomaly reason construction
- Output file generation (CSV, JSON)
- CSV/JSON consistency
- Score range validation
- Empty dataset handling
- PostgreSQL integration

### Database Tests (`test_db_loader.py`)

- PostgreSQL connection
- Schema creation and idempotency
- Table structure verification
- CSV loading and insertion
- Idempotent loading (ON CONFLICT DO NOTHING)
- NULL field storage
- Timestamp format handling
- Special character handling
- Missing file/column error handling

### Analytics Tests (`test_analytics.py`)

- All 13 analytics queries
- Empty table behavior
- NULL value handling
- JSON report serialization
- Format helper functions
- print_report output

### Reporting Tests (`test_reporting.py`)

- Data quality report generation
- Operational report generation
- Final report generation
- Report file creation (JSON, CSV, TXT)
- Empty dataframe handling

### Dashboard Tests (`test_dashboard.py`)

- Data loading (CSV, JSON)
- Filtering (service, log level, event type, anomaly)
- Unique value extraction
- NULL-safe rendering

## Test Data

### Sample Datasets

Located in `tests/data/sample_logs/`:

- `valid_logs.txt` - 10 valid log lines covering all event types
- `malformed_logs.txt` - Mix of valid and malformed lines
- `missing_value_logs.txt` - Logs with varying field completeness
- `duplicate_logs.txt` - Logs with duplicate records
- `anomaly_logs.txt` - Logs with anomaly-indicative patterns

### Test Fixtures

Most test files use inline fixtures for controlled, reproducible testing:

```python
FIXTURE_ROWS = [
    ("2026-09-20 10:00:00.000000", "INFO", "API_REQUEST", "auth",
     "/api/login", "POST", 200, 100, "U100", ""),
    ...
]
```

## PostgreSQL Tests

Tests that require PostgreSQL are decorated with:

```python
@unittest.skipUnless(postgres_available(), "PostgreSQL not available")
```

These tests create and use a dedicated `logflow_test` database that is dropped after the test suite completes.

## Verifying Tests

After making changes, always run:

```bash
python -m compileall -q app run.py dashboard.py
python -m pytest -q --maxfail=0
```

Both must pass before committing.
