#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Run script for RIPTIDAL.

This script provides a convenient way to run the application
directly from the source directory.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import the package
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Import the main function from the package
from riptidal.main import main

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
