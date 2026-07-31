#!/bin/bash

########################
# Script by John Reed  #
# 2026-07-29           #
########################

##################################################################
# Bootstrap a Python 3 venv and install aws-tag-manager deps.      #
##################################################################

set -euo pipefail

# Prefer 3.10+ when available (project requires-python >=3.10).
# Include common Homebrew prefixes — /usr/bin/python3 is often still 3.9.
PY=""
CANDIDATES=(
  python3.14 python3.13 python3.12 python3.11 python3.10
  /opt/homebrew/bin/python3
  /usr/local/bin/python3
  python3
)
for candidate in "${CANDIDATES[@]}"; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
    ver=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue
    major=${ver%%.*}
    minor=${ver#*.}
    if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; }; then
      PY=$candidate
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "need python 3.10+ (project requires-python >=3.10)" >&2
  exit 1
fi

echo "creating virtualenv with $PY..."
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "installing package (editable)..."
pip install --upgrade pip
pip install -e .
pip install -r requirements.txt

echo "venv ready — source .venv/bin/activate then run aws-tag-manager or ./aws_tag_manager.py"
