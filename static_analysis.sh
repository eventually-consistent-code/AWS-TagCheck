#!/bin/bash

################################################################
# Simple way to run python static analysis check on your code. #
# pylint + pycodestyle on the active modules.                  #
################################################################

set -euo pipefail

TARGETS="aws.py aws_tag_manager.py tagmanager"

echo "Running pylint..."
pylint --rcfile pylintrc ${TARGETS}

echo "Running pycodestyle..."
pycodestyle --max-line-length=120 ${TARGETS}

echo "static analysis complete."
