---
status: resolved
issue: 34
created: 2026-07-31
resolved: 2026-07-31
---
# Trace: Phase 5 verify: zone-split's bimodal-ages trigger unreachable (2-band bimodal yields no rec) and MoveManifestEmitter writes unquoted CSV corrupting comma-bearing keys; plus output-surface nits from adversarial pass

## evidence — 2026-07-31
Verifier repros: 50% fresh / 50% >365d single-class prefix → no recommendation (CONTEXT locks "strongly bimodal ages" as a zone-split trigger; implementation needs ≥3 significant bands, so true bimodal never fires). Move-plan CSV for key "logs/comma,name.log" → 4-field row no parser splits (raw f-string write, no quoting — every other writer uses csv.writer or URL-encoding). Nits: truncation not echoed to console, out-of-scope notes and top_owners absent from HTML surfaces, all-conforming rerun says "no objects matched", zero-byte fresh markers read as "no fresh writes".

## verdict — 2026-07-31
Fixed in a15921c: bimodal zone-split now fires on meaningful bytes at both temperature extremes (50/50 test added); move plans write via csv.writer (comma-key roundtrip test); zero-byte fresh markers count as activity; all-conforming reruns say "nothing to move"; truncation echoed; HTML gains top-owners + out-of-scope notes. 186 tests + lint green. Accepted as documented deviations: partial runs eligible for move-plan recs, root-prefix recs dropped silently, first-match overlap resolution, 4-digit date-conformance heuristic.

## resolution — 2026-07-31
Both verifier ISSUEs + four nits fixed in a15921c (bimodal zone-split trigger, csv.writer move plans, zero-byte fresh activity, all-conforming messaging, truncation echo, HTML owners/notes). Remaining nits accepted as documented deviations in VERIFICATION.md. 186 tests + lint green.
