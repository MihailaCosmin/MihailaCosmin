#!/bin/sh
# Acelasi build, pentru Linux si macOS (produce un executabil pentru sistemul curent).
#   ./build_exe.sh                 -> dist/Mixamo2MetaHuman
#   ./build_exe.sh ~/Proiecte      -> si il copiaza acolo
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
[ -d build/_venv ] || "$PYTHON" -m venv build/_venv
. build/_venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller

echo "=== Verific aplicatia ==="
python -m unittest discover -s tests

echo "=== Construiesc executabilul ==="
if [ -n "$1" ]; then
    python build/package.py --dest "$1"
else
    python build/package.py
fi
