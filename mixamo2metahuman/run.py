#!/usr/bin/env python3
"""Porneste aplicatia cu dublu-click sau `python run.py`."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mixamo2mh.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
