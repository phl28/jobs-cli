#!/usr/bin/env python3
"""Entry point for PyInstaller builds.

This module provides an entry point for PyInstaller that uses absolute imports.
The src/main.py uses relative imports which don't work with PyInstaller's
direct execution model.
"""

import sys
import os

# Add the project root to the path to enable absolute imports
if getattr(sys, 'frozen', False):
    # Running as compiled binary
    base_path = sys._MEIPASS
else:
    # Running in development
    base_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_path)

# Now import and run the main function
from src.main import main

if __name__ == "__main__":
    main()
