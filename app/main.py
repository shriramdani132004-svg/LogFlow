import logging
import os

from app.config import INPUT_DIR, LOG_DIR, LOG_LEVEL, OUTPUT_DIR, PROJECT_ROOT


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, "app.log")

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file),
        ],
    )


def ensure_directories():
    for directory in [INPUT_DIR, OUTPUT_DIR, LOG_DIR]:
        os.makedirs(directory, exist_ok=True)


def main():
    setup_logging()
    ensure_directories()

    logger = logging.getLogger(__name__)
    logger.info("LogFlow started successfully")
    logger.info("Project root : %s", PROJECT_ROOT)
    logger.info("Input dir    : %s", INPUT_DIR)
    logger.info("Output dir   : %s", OUTPUT_DIR)
    logger.info("Log dir      : %s", LOG_DIR)
    logger.info("LogFlow foundation is ready")


if __name__ == "__main__":
    main()
