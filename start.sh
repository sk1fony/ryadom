#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Установите Python 3.10 или новее: https://www.python.org/downloads/"
    exit 1
fi
exec python3 bootstrap.py "$@"
