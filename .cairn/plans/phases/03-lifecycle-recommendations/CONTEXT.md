# Phase 3: lifecycle recommendations — Context

## Locked decisions

<!-- decisions made for this phase; on conflict these WIN over tracker issue text -->

- Carried from phase-2 verification: since Sept 2024 AWS's DEFAULT lifecycle
  behavior excludes objects <128 KiB from all transitions. Generated
  lifecycle rules must set `ObjectSizeGreaterThan` explicitly so the rule
  matches what the projections priced (and never silently archives tiny
  objects the floor math excluded).
- Carried from phase-2 verification: Intelligent-Tiering sources may only
  transition to One Zone-IA / Glacier IR / Glacier Flexible / Deep Archive —
  never Standard-IA. Rule generation must enforce the same matrix the
  projector uses (INT_ALLOWED_TARGETS in projections.py).
