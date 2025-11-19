import logging
import os
from pathlib import Path

def setup_error_logger(log_file="logs/error.log", level=logging.ERROR):
    """
    Sets up a dedicated logger with a specified log file and level.
    """
    # Ensure the logs directory exists
    os.makedirs(Path(log_file).parent, exist_ok=True)

    logger = logging.getLogger(log_file) # Use log_file as logger name to avoid conflicts
    logger.setLevel(level)

    # Prevent adding multiple handlers if the logger is already configured
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger