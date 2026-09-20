import logging

import psycopg2
from psycopg2 import OperationalError

from app.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)


def get_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        return conn
    except OperationalError as e:
        msg = str(e)
        if DB_PASSWORD:
            msg = msg.replace(DB_PASSWORD, "***")
        logger.error("Failed to connect to PostgreSQL (host=%s port=%s db=%s user=%s): %s",
                      DB_HOST, DB_PORT, DB_NAME, DB_USER, msg)
        raise


def close_connection(conn):
    if conn and not conn.closed:
        try:
            conn.close()
        except Exception:
            pass


def execute_sql_file(conn, sql_path):
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Executed SQL file: %s", sql_path)
