"""
Purpose: S3 server-access-log parsing — fold REST.GET.OBJECT records into a
per-(bucket, key) last-read index for scan-time age enrichment. Log
delivery is best-effort with hours-scale lag, so derived last-read times
are LOWER BOUNDS, never ground truth.
Author(s): John Reed
"""

import datetime
import logging
import shlex
import urllib.parse

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.access_log")
LOG.setLevel(logging.INFO)


# Constants

READ = "read"
WRITE = "write"

READ_OPERATIONS = ("REST.GET.OBJECT",)
WRITE_OPERATIONS = ("REST.PUT.OBJECT", "REST.POST.OBJECT",
                    "REST.COPY.OBJECT", "REST.DELETE.OBJECT")
TIME_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

# Space-delimited field positions (0-based) in a server access log record —
# the bracketed timestamp splits into TWO tokens (time + tz):
# owner bucket [time tz] remote_ip requester request_id operation key ...
#   0     1      2    3      4         5          6          7      8
F_BUCKET = 1
F_TIME = 2
F_OPERATION = 7
F_KEY = 8


def parse_line(line):
    """
    One log record -> (bucket, key, time, optype) or None.

    optype is READ (REST.GET.OBJECT) or WRITE (PUT/POST/COPY/DELETE);
    other operations, `-` keys, and malformed records return None.

    :param line: raw log line
    :returns: (bucket, decoded key, aware datetime, optype) or None
    """
    try:
        # shlex honors the quoted request/user-agent fields; the bracketed
        # timestamp arrives as two plain tokens which shlex keeps intact.
        parts = shlex.split(line, posix=True)
        operation = parts[F_OPERATION]
        if operation in READ_OPERATIONS:
            optype = READ
        elif operation in WRITE_OPERATIONS:
            optype = WRITE
        else:
            return None
        key = parts[F_KEY]
        if key == "-":
            return None
        stamp = f"{parts[F_TIME]} {parts[F_TIME + 1]}".strip("[]")
        when = datetime.datetime.strptime(stamp, TIME_FORMAT)
        return parts[F_BUCKET], urllib.parse.unquote(key), when, optype
    except (IndexError, ValueError):
        return None


def fold_reads(parsed_iter):
    """
    Fold parsed op records into a newest-READ-wins index.

    Only READ ops count toward last-read; write ops are ignored here.
    Shared by every last-read source (access logs, CloudTrail).

    :param parsed_iter: iterable of (bucket, key, datetime, optype) or None
    :returns: (index dict, read records_used count)
    """
    index = {}
    used = 0
    for parsed in parsed_iter:
        if parsed is None:
            continue
        bucket, key, read_time, optype = parsed
        if optype != READ:
            continue
        used += 1
        existing = index.get((bucket, key))
        if existing is None or read_time > existing:
            index[(bucket, key)] = read_time
    return index, used


def iter_events(paths):
    """
    Yield every parsed op record (not None) from the given log files.

    :param paths: iterable of local access-log file paths
    :yields: (bucket, key, datetime, optype)
    """
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parsed = parse_line(line)
                if parsed is not None:
                    yield parsed


def load_access_index(paths):
    """
    Fold access-log files into {(bucket, key): newest read time}.

    :param paths: iterable of local log file paths
    :returns: (index dict, records_used count)
    """
    paths = list(paths)
    index, used = fold_reads(iter_events(paths))
    LOG.info("access index: %s read events over %s keys from %s file(s).",
             used, len(index), len(paths))
    return index, used
