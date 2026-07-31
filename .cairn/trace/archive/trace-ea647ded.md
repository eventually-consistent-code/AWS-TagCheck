---
status: resolved
issue: 32
created: 2026-07-31
resolved: 2026-07-31
---
# Trace: --age-out-map with unknown storage class crashes with UnknownStorageClass traceback instead of exit 4 (validation leak found in verify re-check)

## evidence — 2026-07-31
Repro: cli.main(["--project-savings","--age-out-map","365=BOGUS"]) raises UnknownStorageClass('BOGUS'). Cause: _parse_age_out_map validates shape only; UnknownStorageClass subclasses KeyError, so _run_projections' except ValueError misses it. Also accepted: 365=STANDARD, an AWS-invalid transition target, priced as a $0 no-op.

## verdict — 2026-07-31
Fixed in 9d2c74f: override targets validated against the pricing snapshot before projection — unknown classes and STANDARD (invalid lifecycle destination) exit 4 with a clear message. Two new CLI test assertions; 123 tests + lint green.

## resolution — 2026-07-31
--age-out-map targets validated against the pricing snapshot; unknown classes and STANDARD exit 4 instead of crashing. Fixed in 9d2c74f, tested, suite green.
