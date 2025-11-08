"""
Path utilities for RIPTIDAL.

This module provides functions for managing paths and directories
used by the application.
"""

import os
import platform
import re
import string
from pathlib import Path
from typing import Dict, Optional, Union, Any


from riptidal.utils.logger import get_logger

def get_project_root() -> Path:
    """
    Get the root directory of the project with enhanced error handling.
    
    Returns:
        Path to the project root directory
    """
    logger = get_logger(__name__)
    
    try:
        # The module file is in utils/paths.py
        # So we need to go up one level to get to the project root
        current_file = Path(__file__).resolve()  # Use resolve() for absolute path
        logger.debug(f"Current file path: {current_file}")
        
        # Verify the expected structure
        if current_file.parent.name != "utils":
            logger.warning(f"Unexpected directory structure: {current_file.parent.name} is not 'utils'")
        
        project_root = current_file.parent.parent
        logger.debug(f"Calculated project root: {project_root}")
        
        # Verify this looks like a project root by checking for common files/directories
        common_markers = ["main.py", "README.md", "pyproject.toml", "requirements.txt"]
        found_markers = [marker for marker in common_markers if (project_root / marker).exists()]
        
        if not found_markers:
            logger.warning(f"Project root may be incorrect, no common markers found: {project_root}")
            # Try one level up as fallback
            alt_root = project_root.parent
            alt_markers = [marker for marker in common_markers if (alt_root / marker).exists()]
            if alt_markers:
                logger.info(f"Using alternative project root: {alt_root} (found markers: {alt_markers})")
                return alt_root
        else:
            logger.debug(f"Verified project root with markers: {found_markers}")
        
        return project_root
    except Exception as e:
        logger.error(f"Error determining project root: {str(e)}", exc_info=True)
        # Fallback to current working directory
        cwd = Path.cwd()
        logger.info(f"Using current working directory as fallback: {cwd}")
        return cwd


def get_config_dir() -> Path:
    """
    Get the configuration directory for the application.
    
    Returns:
        Path to the configuration directory
    """
    # Store config in a .config directory in the project root
    config_dir = get_project_root() / ".config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_data_dir() -> Path:
    """
    Get the data directory for the application with enhanced error handling.
    
    Returns:
        Path to the data directory
    """
    logger = get_logger(__name__)
    
    try:
        # Get the project root
        project_root = get_project_root()
        logger.debug(f"Project root: {project_root}")
        
        # Store data in a .data directory in the project root
        data_dir = project_root / ".data"
        logger.debug(f"Data directory path: {data_dir}")
        
        # Create the directory with explicit error handling
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created or verified data directory: {data_dir}")
        except PermissionError:
            logger.error(f"Permission denied when creating data directory: {data_dir}")
            # Try to create in user's home directory as fallback
            home_data_dir = Path.home() / ".riptidal_data"
            logger.info(f"Attempting to use fallback data directory: {home_data_dir}")
            home_data_dir.mkdir(parents=True, exist_ok=True)
            return home_data_dir
        except Exception as e:
            logger.error(f"Error creating data directory: {str(e)}")
            raise
        
        # Verify the directory exists and is writable
        if not data_dir.exists():
            logger.error(f"Data directory does not exist after creation attempt: {data_dir}")
            raise IOError(f"Failed to create data directory: {data_dir}")
        
        # Check if directory is writable by creating a test file
        test_file = data_dir / ".write_test"
        try:
            with open(test_file, "w") as f:
                f.write("test")
            test_file.unlink()  # Remove the test file
            logger.debug(f"Verified data directory is writable: {data_dir}")
        except Exception as e:
            logger.error(f"Data directory is not writable: {data_dir}, error: {str(e)}")
            # Try to use home directory as fallback
            home_data_dir = Path.home() / ".riptidal_data"
            logger.info(f"Using fallback data directory: {home_data_dir}")
            home_data_dir.mkdir(parents=True, exist_ok=True)
            return home_data_dir
        
        return data_dir
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Error in get_data_dir: {str(e)}", exc_info=True)
        # Last resort fallback
        fallback_dir = Path.home() / ".riptidal_data"
        logger.info(f"Using emergency fallback data directory: {fallback_dir}")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir


def get_cache_dir() -> Path:
    """
    Get the cache directory for the application.
    
    Returns:
        Path to the cache directory
    """
    # Store cache in a .cache directory in the project root
    cache_dir = get_project_root() / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_default_download_dir() -> Path:
    """
    Get the default download directory for the application.
    
    Returns:
        Path to the default download directory
    """
    # Store downloads in a Downloads directory in the project root
    download_dir = get_project_root() / "Downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it's valid across different operating systems.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        A sanitized filename
    """
    # Replace invalid characters with underscores
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove C0 and C1 control characters, but allow other Unicode characters.
    # C0 controls: U+0000 to U+001F
    # C1 controls: U+007F to U+009F (DEL is U+007F)
    # We'll create a regex to remove these.
    # This regex matches characters in the C0 range (0-31) and C1 range (127-159).
    control_chars_re = re.compile(r'[\x00-\x1f\x7f-\x9f]')
    filename = control_chars_re.sub('', filename)
    
    # Trim leading/trailing whitespace and dots
    filename = filename.strip(' .')
    
    # Ensure the filename isn't empty
    if not filename:
        filename = "unnamed"
    
    # Ensure the filename isn't too long (255 is the limit on many filesystems)
    if len(filename) > 250:
        # Keep the extension if present
        parts = filename.rsplit('.', 1)
        if len(parts) > 1 and len(parts[1]) <= 10:
            filename = parts[0][:250 - len(parts[1]) - 1] + '.' + parts[1]
        else:
            filename = filename[:250]
    
    return filename


def format_path(
    template: str, 
    data: Dict[str, Any], 
    base_dir: Optional[Union[str, Path]] = None
) -> Path:
    """
    Format a path template with the provided data.
    
    Args:
        template: The path template with placeholders
        data: Dictionary of values to substitute in the template
        base_dir: Optional base directory to prepend to the path
        
    Returns:
        A formatted Path object
    """
    # Replace placeholders in the template
    formatted = template
    for key, value in data.items():
        if value is not None:
            placeholder = f"{{{key}}}"
            if placeholder in formatted:
                # Sanitize the value if it's a string
                if isinstance(value, str):
                    value = sanitize_filename(value)
                formatted = formatted.replace(placeholder, str(value))
    
    # Remove any remaining placeholders
    formatted = re.sub(r'{[^{}]*}', '', formatted)
    
    # Clean up multiple slashes and normalize the path
    formatted = re.sub(r'[/\\]+', os.path.sep, formatted)
    
    # Remove leading/trailing slashes
    formatted = formatted.strip(os.path.sep)
    
    # Create the path
    if base_dir:
        path = Path(base_dir) / formatted
    else:
        path = Path(formatted)
    
    return path
