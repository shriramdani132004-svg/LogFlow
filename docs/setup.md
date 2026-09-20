# LogFlow Setup Guide

## Prerequisites

- Python 3.10+
- PostgreSQL 14+
- pip (Python package manager)

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd LogFlow Application Log Processing & Anomaly Detection Pipeline
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL

Create the database:

```bash
createdb -U postgres logflow
```

### 5. Configure environment

Create a `.env` file in the project root:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=logflow
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_BATCH_SIZE=500
```

**Important**: Never commit your `.env` file to version control.

## Running the Pipeline

### Step-by-step execution

```bash
# 1. Generate sample logs (default: 100 records)
python run.py generate --records 500

# 2. Ingest raw logs
python run.py ingest

# 3. Parse, validate, and clean logs
python run.py process

# 4. Initialize database schema
python run.py db-init

# 5. Load cleaned data into PostgreSQL
python run.py db-load

# 6. Verify database contents
python run.py db-verify

# 7. Run SQL analytics
python run.py analyze

# 8. Run anomaly detection
python run.py detect

# 9. Generate final reports
python run.py report
```

### Launching the dashboard

```bash
streamlit run dashboard.py
```

The dashboard opens at http://localhost:8501

## Running Tests

```bash
python -m pytest -q
```

For verbose output:

```bash
python -m pytest -v
```

## Project Structure

```
LogFlow/
├── app/
│   ├── config.py           # Environment and path configuration
│   ├── log_generator.py    # Synthetic log generation
│   ├── ingestion.py        # Raw log file reading
│   ├── log_parser.py       # Log line parsing
│   ├── processor.py        # Validation, cleaning, deduplication
│   ├── database.py         # PostgreSQL connection management
│   ├── db_loader.py        # CSV-to-database loading
│   ├── analytics.py        # SQL analytics queries
│   ├── anomaly_detection.py # ML anomaly detection
│   └── reporting.py        # Report generation
├── dashboard.py            # Streamlit web dashboard
├── run.py                  # CLI entry point
├── sql/
│   ├── schema.sql          # Database schema
│   └── analytics.sql       # Analytics queries
├── tests/                  # Test suite
├── docs/                   # Documentation
├── data/
│   ├── input/              # Raw log files
│   └── output/             # Generated outputs
├── .env                    # Environment variables (not committed)
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

## Troubleshooting

### PostgreSQL connection refused

Ensure PostgreSQL is running:

```bash
pg_isready
```

### Authentication failed

Verify your password in `.env` matches your PostgreSQL password.

### Database does not exist

```bash
createdb -U postgres logflow
```

### Missing streamlit

```bash
pip install streamlit>=1.30
```
