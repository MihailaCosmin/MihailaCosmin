"""Punct de intrare pentru executabilul din linia de comanda."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mixamo2mh.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
