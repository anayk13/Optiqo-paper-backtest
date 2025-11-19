import logging
import os
from threading import Lock
from datetime import date
from logging.handlers import RotatingFileHandler
# import apscheduler # This import still seems unused unless you have plans for it elsewhere

DEFAULT_LOG_HANDLER = 'logs' 

_logger_lock = Lock()
_loggers = {} # To store initialized loggers


class DailyFileHandler(logging.FileHandler):
    """Custom FileHandler that creates a new log file every day."""

    def  __init__(self, log_dir, mode='a', encoding=None, delay=False):
        self.log_dir = log_dir
        self.current_date = date.today()
        filename = os.path.join(self.log_dir, self._get_filename())
        super().__init__(filename, mode, encoding, delay)

    def _get_filename(self):
        return f'{self.current_date}.log'
    
    def emit(self, record):
        try:
            self.acquire()
            new_date = date.today()

            if new_date != self.current_date:
                self.current_date = new_date
                self.close()
                self.baseFilename = os.path.abspath(
                    os.path.join(self.log_dir, self._get_filename())
                )
                self.stream = self._open()
            else:
                if self.stream is None:
                    self.stream = self._open()

            super().emit(record)
        finally:
            self.release()


class ContextFilter(logging.Filter):
    """ContextFilter to add broker_name, account_name, and strategy_name in every log record."""

    def __init__(self, broker_name, account_name, strategy_name='N/A'):
        super().__init__()
        self.broker_name = broker_name
        self.account_name = account_name
        self.strategy_name = strategy_name

    def filter(self, record):
        record.broker_name = self.broker_name
        record.account_name = self.account_name
        record.strategy_name = self.strategy_name
        return True
    
def get_logger(main_folder_name: str = '', broker_name: str = 'SYSTEM', account_name: str = 'N/A', 
               strategy_name: str = 'N/A', level: int = logging.INFO) -> logging.Logger: # <--- ADDED 'level' ARG
    """Returns a logger instance with file and console handlers."""

    logger_name = f'{main_folder_name}_{broker_name}_{account_name}_{strategy_name}'
    
    with _logger_lock:
        if logger_name not in _loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level) # <--- USE THE 'level' ARG HERE
            

            log_sub_dir = os.path.join(DEFAULT_LOG_HANDLER, broker_name, account_name, strategy_name, main_folder_name)
            os.makedirs(log_sub_dir, exist_ok=True)
            
            context_filter = ContextFilter(broker_name, account_name, strategy_name)
            if not any(isinstance(f, ContextFilter) and f.broker_name == broker_name and f.account_name == account_name and f.strategy_name == strategy_name for f in logger.filters):
                 logger.addFilter(context_filter)

            file_handler = DailyFileHandler(log_sub_dir)
            file_handler.setLevel(level) # <--- USE THE 'level' ARG HERE
            file_formatter = logging.Formatter(
                '%(broker_name)s - %(account_name)s - %(strategy_name)s - %(asctime)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level) # <--- USE THE 'level' ARG HERE
            console_formatter = logging.Formatter(
                '%(broker_name)s - %(account_name)s - %(strategy_name)s - %(asctime)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)

            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            
            _loggers[logger_name] = logger
        
        # If logger already exists, ensure its level is set correctly
        _loggers[logger_name].setLevel(level)
        for handler in _loggers[logger_name].handlers:
            handler.setLevel(level)

        return _loggers[logger_name]