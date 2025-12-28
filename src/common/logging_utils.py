"""
Enterprise JSON Logging Utilities.

Provides structured JSON logging for Lambda and Glue jobs,
enabling queryability in CloudWatch Logs Insights and Splunk.
"""
import json
import logging
import traceback


class JsonFormatter(logging.Formatter):
    """
    Formats log records as JSON for machine-readable logs.
    Includes level, message, timestamp, logger name, and location.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
            "location": f"{record.filename}:{record.lineno}"
        }
        if record.exc_info:
            log_record["exception"] = "".join(traceback.format_exception(*record.exc_info))
        # Include any extra fields passed to the logger
        if hasattr(record, '__dict__'):
            extras = {k: v for k, v in record.__dict__.items() 
                     if k not in ('name', 'msg', 'args', 'created', 'filename', 
                                 'funcName', 'levelname', 'levelno', 'lineno', 
                                 'module', 'msecs', 'pathname', 'process', 
                                 'processName', 'relativeCreated', 'stack_info',
                                 'thread', 'threadName', 'exc_info', 'exc_text',
                                 'message', 'taskName')}
            if extras:
                log_record["extra"] = extras
        return json.dumps(log_record)


def setup_logger(name: str = None) -> logging.Logger:
    """
    Configure and return a logger with JSON formatting.
    
    Args:
        name: Optional logger name. If None, returns root logger.
    
    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
    
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    return logger


class ApiError(Exception):
    """Custom exception for API-related errors."""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
