"""
Logging utilities for RIPTIDAL.

This module provides functions for setting up and configuring logging
throughout the application.
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Union, TextIO


def setup_logger(
    level: int = logging.INFO,
    log_file: Optional[Union[str, Path]] = None,
    file_level: Optional[int] = None,
    format_string: Optional[str] = None,
    stream: Optional[TextIO] = None,
) -> None:
    """
    Set up the logger for the application.
    
    Args:
        level: The logging level for the console handler
        log_file: Optional path to a log file
        file_level: Optional logging level for the file handler (defaults to level)
        format_string: Optional custom format string for log messages
        stream: Optional stream to use for console logging (defaults to sys.stdout)
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all logs at the root level
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set default format if not provided
    if format_string is None:
        format_string = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
    
    formatter = logging.Formatter(format_string)
    
    # Console handler
    console_handler = logging.StreamHandler(stream or sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if requested)
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(file_level or logging.DEBUG)  # Always log DEBUG to file
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Suppress overly verbose logs from libraries
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Log the setup
    logger = logging.getLogger(__name__)
    logger.debug(f"Logging initialized at level {logging.getLevelName(level)}")
    if log_file:
        logger.debug(f"Log file: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the specified name.
    
    This is a convenience function that ensures all loggers
    are obtained consistently throughout the application.
    
    Args:
        name: The name of the logger
        
    Returns:
        A logger instance
    """
    return logging.getLogger(name)
