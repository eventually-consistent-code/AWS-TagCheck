---
status: resolved
issue: 18
created: 2026-07-31
resolved: 2026-07-31
---
# Trace: Phase 3 verify: lint gate red — pylint 8.36 with E0611 no-name-in-module flood across tagmanager submodules; static_analysis.sh exits nonzero

## evidence — 2026-07-31
./static_analysis.sh → pylint 8.36/10, ~28x E0611 "No name 'X' in module 'tagmanager'" across serve.py, scanner.py, app/, providers/, models/, rules/; set -euo pipefail kills script before pycodestyle. Runtime imports fine — pytest 82 passed.

## hypothesis — 2026-07-31
Repo-root __init__.py (`__all__ = ['aws']`, initial-commit relic) makes pylint treat the working dir as a package, corrupting resolution of the tagmanager package → E0611 on every submodule import. Nothing references it: pyproject py-modules = [aws_tag_manager, aws], packages = tagmanager.*.

## test — 2026-07-31
mv __init__.py aside → ./static_analysis.sh: pylint 10.00/10, pycodestyle clean, exit 0; pytest 82 passed. Restored file → red again. Single-cause confirmed.

## verdict — 2026-07-31
Root cause confirmed: stray repo-root __init__.py. Fix: git rm __init__.py (commit on master). Post-fix: static_analysis.sh exit 0, pylint 10.00/10, pycodestyle clean, 82 tests pass.

## resolution — 2026-07-31
Deleted stray repo-root __init__.py (initial-commit relic, nothing imported it). Lint gate green: pylint 10.00, pycodestyle clean, 82/82 tests pass.
