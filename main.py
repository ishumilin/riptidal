#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RIPTIDAL - Main Entry Point

This module serves as the entry point for the RIPTIDAL application.
It initializes the application, parses command-line arguments, and starts the
appropriate interface based on user input.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from riptidal.core.settings import Settings, load_settings
from riptidal.ui.cli import CLI
from riptidal.utils.logger import setup_logger
from riptidal.utils.paths import get_data_dir

# Import version directly to avoid circular imports
__version__ = "0.2.7"


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="RIPTIDAL - Download music from Tidal"
    )
    parser.add_argument(
        "-v", "--version", action="store_true", help="Show version information"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "-c", "--config", type=str, help="Path to custom config file"
    )
    parser.add_argument(
        "-o", "--output", type=str, help="Output directory for downloads"
    )
    
    return parser.parse_args()


async def main() -> int:
    """Main entry point for the application."""
    args = parse_arguments()
    
    # Setup logging - always enable debug logging to file
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_file = get_data_dir() / "tidal_dl.log"
    setup_logger(log_level, log_file)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting RIPTIDAL")
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Application version: {__version__}")
    
    # Show version if requested
    if args.version:
        # Use the version defined at the top of this file
        print(f"RIPTIDAL v{__version__}")
        return 0
    
    # Load settings
    config_path = args.config if args.config else None
    settings = load_settings(config_path)
    logger.debug(f"Loaded settings: {settings}")
    
    # Override output directory if specified
    if args.output:
        settings.download_path = Path(args.output)
        logger.debug(f"Override download path: {settings.download_path}")
    
    # Start CLI interface
    cli = CLI(settings)
    return await cli.start()


def main_cli() -> None:
    """
    Entry point for the command-line interface.
    
    This function is used as the entry point for the console_scripts
    in setup.py. It wraps the async main function and handles exceptions.
    """
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logging.getLogger(__name__).exception("Unhandled exception")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
