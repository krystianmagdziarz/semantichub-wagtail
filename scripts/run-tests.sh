#!/usr/bin/env bash
# Runs what CI runs: ruff, the migrations check and pytest.
#
#   bash scripts/run-tests.sh
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ruff check .
ruff format --check .
DJANGO_SETTINGS_MODULE=tests.settings PYTHONPATH=. \
	python -m django makemigrations --check --dry-run semantichub_wagtail
python -m pytest -q
