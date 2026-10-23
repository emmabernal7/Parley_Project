#!/usr/bin/env python3
"""Start SportsQuant.  Usage:  python run.py
See README.md for first-time setup (Python version, installing dependencies, getting real
history with scripts/ingest.py, and optional API keys in .env)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    from sportsquant.web.app import main
    main()
