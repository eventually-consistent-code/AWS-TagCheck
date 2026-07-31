---
status: open
issue: 33
created: 2026-07-31
---
# Trace: Phase 4 verify: print_summary hardcodes s3:// URI prefix on oldest-objects lines — wrong for azure/gcs/fs backends

## evidence — 2026-07-31
Live fs scan output: "s3:///private/tmp/.../fsdemo/archive/2019/dump.bin" — print_summary formats every oldest-object line as s3://{container}/{key} regardless of backend. Data correct; label wrong for azure/gcs/fs.
