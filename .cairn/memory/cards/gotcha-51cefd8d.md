---
type: gotcha
provenanceFiles: [static_analysis.sh, pyproject.toml]
provenanceCommits: [b8f6e3c, b8f6e3c]
created: 2026-07-31
confidence: high
---
A repo-root __init__.py (initial-commit relic, __all__ = ['aws']) made pylint treat the repo root as a package and corrupted resolution of the tagmanager package — E0611 "no name in module" on every submodule import, pylint 8.36, static_analysis.sh exit nonzero, while runtime imports and all 82 tests stayed green. Removed in b8f6e3c. Never reintroduce a root-level __init__.py; the canonical lint gate is ./static_analysis.sh (pylint --rcfile pylintrc + pycodestyle, set -euo pipefail).
