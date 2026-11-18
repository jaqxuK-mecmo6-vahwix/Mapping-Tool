#!/usr/bin/env bash
# Runs the pipeline with a virtualenv OUTSIDE the project folder, because the folder name contains ':'
# which breaks PROJ (it uses ':' as a search-path separator) and uv's PATH handling.
#   ./run.sh build      -> download (cached) + build all layers into data/build
#   ./run.sh validate   -> validation checks, writes data/build/validation_report.json
#   ./run.sh test       -> unit tests
#   ./run.sh xcheck     -> independent circle totals for VALIDATION.md (data/build/xcheck.json)
set -euo pipefail
cd "$(dirname "$0")"
export UV_PROJECT_ENVIRONMENT="${RADIUSSTATS_VENV:-$HOME/.local/share/radiusstats-europe/venv}"
uv sync -q
PY="$UV_PROJECT_ENVIRONMENT/bin/python"
export PYTHONPATH="$PWD"
case "${1:-build}" in
  build)    shift || true; exec "$PY" -m radiusstats_pipeline.cli "$@" ;;
  validate) exec "$PY" -m radiusstats_pipeline.validate ;;
  test)     shift; exec "$PY" -m pytest -q "$@" ;;
  xcheck)   exec "$PY" -m radiusstats_pipeline.xcheck ;;
  *) echo "usage: $0 build|validate|test|xcheck" >&2; exit 2 ;;
esac
