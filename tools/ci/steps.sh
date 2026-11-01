#!/usr/bin/env bash
# The suite, the way CI runs it, in the folder it is started in: tools/ci-local.mjs runs this inside a container shaped
# like a GitHub runner, so what it finds is what a push would find. The workflow installs through its own cached steps
# and ends in the same last line.
set -euo pipefail
. tools/ci/versions.env
venv="${CI_VENV:-/tmp/ci-venv}"
python3 -m venv "$venv" 2>/dev/null || virtualenv -q "$venv"   # Playwright's image has virtualenv, not ensurepip
. "$venv/bin/activate"
pip install --quiet --no-input -r tools/ci/requirements.txt "uv==$UV_VERSION"
npm ci --no-fund --no-audit
export DATA_UI_PYTHON="$(command -v python)" DATA_UI_KPI_PUBLISH=0
node tools/test-all.mjs --strict
