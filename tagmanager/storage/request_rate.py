"""
Purpose: Per-prefix request-rate estimation from access-log / CloudTrail
op events. Rates are AVERAGE req/s over the observed sample window — never
the peak the AWS per-prefix ceilings are measured against, so every
consumer must carry the average-vs-peak caveat. A minimum-window guard
keeps a handful of ops over a few minutes from dividing into garbage.
Author(s): John Reed
"""

from dataclasses import dataclass

from tagmanager.storage.access_log import READ
from tagmanager.storage.rollup import prefix_at_depth

# Constants

# AWS S3 per-partitioned-prefix request ceilings (peak per second).
READ_CEILING_RPS = 5500
WRITE_CEILING_RPS = 3500
# Trust no rate derived from a sample shorter than this (seconds).
DEFAULT_MIN_WINDOW_SECONDS = 3600


@dataclass
class RatePrefixStat:
    """Op counts + observed time window for one (container, prefix)."""

    read_count: int = 0
    write_count: int = 0
    window_start: object = None  # aware datetime
    window_end: object = None

    def observe(self, when, optype):
        """Fold one op event into the counts and window."""
        if optype == READ:
            self.read_count += 1
        else:
            self.write_count += 1
        if self.window_start is None or when < self.window_start:
            self.window_start = when
        if self.window_end is None or when > self.window_end:
            self.window_end = when

    def window_seconds(self):
        """Observed sample window in seconds (0 when a single instant)."""
        if self.window_start is None or self.window_end is None:
            return 0.0
        return (self.window_end - self.window_start).total_seconds()


def fold_rates(parsed_iter, prefix_depth):
    """
    Fold parsed op records into per-(container, prefix) rate stats.

    :param parsed_iter: iterable of (bucket, key, datetime, optype) or None
    :param prefix_depth: path segments to roll prefixes up to (the run's)
    :returns: dict of (container, prefix) -> RatePrefixStat
    """
    stats = {}
    for parsed in parsed_iter:
        if parsed is None:
            continue
        bucket, key, when, optype = parsed
        prefix = prefix_at_depth(key, prefix_depth)
        stat = stats.setdefault((bucket, prefix), RatePrefixStat())
        stat.observe(when, optype)
    return stats


def estimate_rates(rate_stats, min_window_seconds=DEFAULT_MIN_WINDOW_SECONDS):
    """
    Turn per-prefix op counts into average req/s, guarding short samples.

    Prefixes whose sample window is below the guard are OMITTED — the
    counts alone can't be trusted as a rate.

    :param rate_stats: fold_rates() output
    :param min_window_seconds: minimum trusted sample window
    :returns: JSON-friendly dict {"container/prefix": {container, prefix,
        read_rps, write_rps, window_s, sample_ops}} — key is "container"
        when prefix is empty. Each value carries container/prefix
        EXPLICITLY so consumers never re-split the key (container paths
        can contain slashes on the fs backend).
    """
    out = {}
    for (container, prefix), stat in rate_stats.items():
        window = stat.window_seconds()
        if window <= 0 or window < min_window_seconds:
            continue
        loc = f"{container}/{prefix}" if prefix else container
        out[loc] = {
            "container": container,
            "prefix": prefix,
            "read_rps": round(stat.read_count / window, 4),
            "write_rps": round(stat.write_count / window, 4),
            "window_s": round(window, 1),
            "sample_ops": stat.read_count + stat.write_count,
        }
    return out
