import os

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

INPUT_DIR = os.path.join(PROJECT_ROOT, "data", "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
SQL_DIR = os.path.join(PROJECT_ROOT, "sql")

LOG_LEVEL = os.environ.get("LOGFLOW_LOG_LEVEL", "INFO")

RAW_LOG_FILE = os.path.join(INPUT_DIR, "application.log")
DEFAULT_RECORD_COUNT = 100
RANDOM_SEED = 42

CLEANED_OUTPUT = os.path.join(OUTPUT_DIR, "cleaned_logs.csv")

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "logflow")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_BATCH_SIZE = int(os.environ.get("DB_BATCH_SIZE", "500"))
