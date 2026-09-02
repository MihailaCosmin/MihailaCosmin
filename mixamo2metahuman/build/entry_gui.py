"""Punct de intrare pentru executabilul cu interfata grafica."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mixamo2mh.gui import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
