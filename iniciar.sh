#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 -c 'import sys; assert sys.version_info >= (3,12), "Instale Python 3.12 ou superior"'
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if [ ! -f .venv/finance-os-installed ]; then
    .venv/bin/python -m pip install -r requirements.lock.txt
    touch .venv/finance-os-installed
fi
exec .venv/bin/python launcher.py "$@"
