#!/usr/bin/env bash
set -euo pipefail

echo "=== Ruff check ==="
ruff check src/ tests/

echo "=== Ruff format check ==="
ruff format --check src/ tests/

echo "=== Mypy ==="
mypy src/

echo "=== All checks passed ==="
