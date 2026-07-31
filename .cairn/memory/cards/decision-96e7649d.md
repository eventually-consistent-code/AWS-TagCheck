---
type: decision
provenanceFiles: [tagmanager/serve.py, tagmanager/config.py]
provenanceCommits: [5593b36, a6f40ba]
created: 2026-07-31
confidence: high
---
Auth fails closed: an unrecognized auth_mode value refuses to serve rather than falling through to open access (5593b36). Auth stack is OIDC with session middleware plus an explicit dev bypass mode (015c87d); a Task-13 review also corrected the OIDC setting name (a6f40ba). Any new auth_mode must be added to the explicit allowlist — never default-permit.
