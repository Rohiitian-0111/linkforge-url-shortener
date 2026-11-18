#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
command -v docker >/dev/null 2>&1 || { echo 'Install and start Docker first.'; exit 1; }
python3 scripts/setup.py
exec docker compose up --build
