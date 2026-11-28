#!/usr/bin/env python3
"""Entry point:  python3 tools/eda/rrkicad.py build|check|sch electronics/<board>/board.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rrkicad.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
