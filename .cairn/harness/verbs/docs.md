---
verb: docs
args: "publish [--name \"<project>\"] | (none = status)"
status: live
---

Mirror the repo's documentation into the configured docs connector
(`docs:` block in cairn.json — Confluence first; Notion/GitBook/Slite/
SharePoint land as future adapters behind the same SPI).

- **(no args) — status:** `docs_status()`. Not configured → say so and show
  the cairn.json `docs:` block shape (see templates/cairn.json.example,
  `_docs`). Configured → report the connector and the landing page (title +
  link) or "not yet published".
- **publish:** `docs_publish(projectName?)` — the project gets a FOLDER named
  after it under the space root; README.md becomes the landing page inside
  that folder, `docs/` (+ root CHANGELOG.md) becomes
  the child page tree, and the landing page gains a Documentation contents
  section. Idempotent: re-publish updates pages in place. `--name` overrides
  the project name (default: repo dir name). Report the page count and the
  landing page link. Title conflicts elsewhere in the space publish under a
  "Title (Context)" suffix — mention any the result surfaces.
- **Pairing:** run after `distill` — distill synthesizes plans + memory into
  `docs/`; `docs publish` mirrors that output (plus the README) outward.
  Removed local files are NOT deleted remotely; note stale pages for manual
  cleanup when the tree shrinks.
- **Errors:** `CONFIG_MISSING` → show the `docs:` block shape.
  `AUTH_MISSING` → surface the env-var names from the message (Confluence
  shares Atlassian API tokens with Jira — same-site users can point the env
  names at their Jira credentials).
