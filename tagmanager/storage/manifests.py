"""
Purpose: Streaming manifest emitters — key-level artifacts written DURING a
scan (rollups keep no keys, so this is the only honest source). Delete
manifests chunk at the delete-objects API limit of 1,000 keys per request.
Nothing here calls AWS; files are proposals a human applies.
Author(s): John Reed
"""

import datetime
import json
import pathlib
import urllib.parse

# Constants

DELETE_CHUNK_SIZE = 1000
BATCH_COPY_MAX_BYTES = 5 * 1024 ** 3

DELETE_APPLY_NOTES = [
    "Manifests are a point-in-time proposal from this scan — objects "
    "modified since no longer match.",
    "Versioned buckets: delete-objects without VersionId creates delete "
    "markers; it does not remove versions.",
    "Apply per chunk:",
    "```bash",
    "aws s3api delete-objects --bucket <bucket> --delete "
    "file://<bucket>.delete-0001.json",
    "```",
]


class DeleteManifestEmitter:
    """
    Fold scan-streamed objects into chunked delete-objects JSON files.

    Objects at or past the stale threshold land in per-bucket chunks of at
    most 1,000 keys ({"Objects": [{"Key": ...}], "Quiet": true}) — the
    hard delete-objects API limit.
    """

    def __init__(self, out_dir, stale_after_days, now=None,
                 chunk_size=DELETE_CHUNK_SIZE):
        """
        :param out_dir: directory manifests are written into
        :param stale_after_days: age threshold in days (>= is stale)
        :param now: timezone-aware "now" for age math (default: UTC now)
        :param chunk_size: keys per manifest file
        """
        self.out_dir = pathlib.Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.stale_after_days = stale_after_days
        self.now = now or datetime.datetime.now(datetime.timezone.utc)
        self.chunk_size = chunk_size
        self._pending = {}
        self._counts = {}
        self._files = {}

    def offer(self, obj):
        """
        Consider one streamed object; buffer it when stale.

        :param obj: StorageObject
        """
        age_days = (self.now - obj.last_modified).total_seconds() / 86400.0
        if age_days < self.stale_after_days:
            return
        bucket = self._pending.setdefault(obj.container, [])
        bucket.append({"Key": obj.key})
        self._counts[obj.container] = self._counts.get(obj.container, 0) + 1
        if len(bucket) >= self.chunk_size:
            self._flush(obj.container)

    def _flush(self, container):
        """Write the buffered chunk for one bucket and reset the buffer."""
        objects = self._pending.get(container)
        if not objects:
            return
        seq = self._files.get(container, 0) + 1
        self._files[container] = seq
        path = self.out_dir / f"{container}.delete-{seq:04d}.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"Objects": objects, "Quiet": True}, handle, indent=2)
            handle.write("\n")
        self._pending[container] = []

    def close(self):
        """
        Flush remainders and report what was written.

        :returns: dict of bucket -> {"files": n, "keys": n}
        """
        for container in list(self._pending):
            self._flush(container)
        return {container: {"files": self._files.get(container, 0),
                            "keys": count}
                for container, count in self._counts.items()}


class MoveManifestEmitter:
    """
    Stream objects into old-key,new-key move plans driven by a prior
    run's structure recommendations (two-pass flow: scan → recommend →
    rescan with this emitter). Copy+delete semantics — the tool moves
    nothing.
    """

    MOVABLE_KINDS = ("date-split", "zone-split")

    def __init__(self, out_dir, recs, stale_after_days, now=None):
        """
        :param out_dir: directory move plans are written into
        :param recs: structure_recs dicts from the latest COMPLETE run
        :param stale_after_days: first age threshold (zone-split moves
            only objects at least this stale)
        :param now: timezone-aware "now" (default: UTC now)
        """
        self.out_dir = pathlib.Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.now = now or datetime.datetime.now(datetime.timezone.utc)
        self.stale_after_days = stale_after_days
        self._recs = [rec for rec in recs
                      if rec.get("kind") in self.MOVABLE_KINDS
                      and rec.get("prefix")]
        self._handles = {}
        self._counts = {}
        self._skipped_conforming = 0

    def _rec_for(self, obj):
        """The first movable recommendation matching this object."""
        for rec in self._recs:
            if (obj.container == rec["container"]
                    and obj.key.startswith(rec["prefix"] + "/")):
                return rec
        return None

    def _new_key(self, obj, rec):
        """
        Rewritten key, or None when the key already conforms.

        date-split injects year/month from last-modified; zone-split
        prefixes a cold/ zone (stale objects only).
        """
        prefix = rec["prefix"]
        rest = obj.key[len(prefix) + 1:]
        if rec["kind"] == "date-split":
            stamp = obj.last_modified
            if rest[:4].isdigit() and rest[4:5] == "/":
                return None  # already date-partitioned
            return f"{prefix}/{stamp.year:04d}/{stamp.month:02d}/{rest}"
        # zone-split
        if obj.key.startswith("cold/"):
            return None
        age_days = (self.now - obj.last_modified).total_seconds() / 86400.0
        if obj.last_accessed is not None:
            accessed_age = ((self.now - obj.last_accessed).total_seconds()
                            / 86400.0)
            age_days = min(age_days, accessed_age)
        if age_days < self.stale_after_days:
            return None  # hot side of the zone split stays put
        return f"cold/{obj.key}"

    def offer(self, obj):
        """
        Consider one streamed object; write a move line when flagged.

        :param obj: StorageObject
        """
        rec = self._rec_for(obj)
        if rec is None:
            return
        new_key = self._new_key(obj, rec)
        if new_key is None:
            self._skipped_conforming += 1
            return
        if obj.container not in self._handles:
            path = self.out_dir / f"{obj.container}.move-plan.csv"
            # Streaming writer — closed in close().
            # pylint: disable-next=consider-using-with
            self._handles[obj.container] = open(path, "w", encoding="utf-8")
            self._handles[obj.container].write("old_key,new_key\n")
        self._handles[obj.container].write(f"{obj.key},{new_key}\n")
        self._counts[obj.container] = self._counts.get(obj.container, 0) + 1

    def close(self):
        """
        Close files and report what was planned.

        :returns: dict of bucket -> {"moves": n} plus "_skipped_conforming"
        """
        for handle in self._handles.values():
            handle.close()
        summary = {container: {"moves": count}
                   for container, count in self._counts.items()}
        if summary:
            summary["_skipped_conforming"] = self._skipped_conforming
        return summary


class BatchCopyEmitter:
    """
    Stream stale objects into S3 Batch Operations copy manifests
    (S3BatchOperations_CSV_20180820: bucket,key with URL-encoded keys).

    Batch copy handles objects up to 5 GB — larger ones land in a sidecar
    skip list instead of poisoning the job.
    """

    def __init__(self, out_dir, stale_after_days, now=None):
        """
        :param out_dir: directory manifests are written into
        :param stale_after_days: age threshold in days (>= is stale)
        :param now: timezone-aware "now" for age math (default: UTC now)
        """
        self.out_dir = pathlib.Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.stale_after_days = stale_after_days
        self.now = now or datetime.datetime.now(datetime.timezone.utc)
        self._handles = {}
        self._skip_handles = {}
        self._counts = {}
        self._skipped = {}

    def _handle_for(self, container, registry, suffix):
        """Open (once) and return the output handle for a bucket."""
        if container not in registry:
            path = self.out_dir / f"{container}{suffix}"
            # Streaming writer — closed in close(); with-block can't span
            # the emitter's lifetime.
            # pylint: disable-next=consider-using-with
            registry[container] = open(path, "w", encoding="utf-8")
        return registry[container]

    def offer(self, obj):
        """
        Consider one streamed object; write a manifest line when stale.

        :param obj: StorageObject
        """
        age_days = (self.now - obj.last_modified).total_seconds() / 86400.0
        if age_days < self.stale_after_days:
            return
        if obj.size_bytes > BATCH_COPY_MAX_BYTES:
            handle = self._handle_for(obj.container, self._skip_handles,
                                      ".batch-copy.skipped.txt")
            handle.write(f"{obj.key}\t{obj.size_bytes}\n")
            self._skipped[obj.container] = (
                self._skipped.get(obj.container, 0) + 1)
            return
        handle = self._handle_for(obj.container, self._handles,
                                  ".batch-copy.csv")
        encoded_key = urllib.parse.quote(obj.key, safe="/")
        handle.write(f"{obj.container},{encoded_key}\n")
        self._counts[obj.container] = self._counts.get(obj.container, 0) + 1

    def close(self):
        """
        Close every open file and report what was written.

        :returns: dict of bucket -> {"keys": n, "skipped_large": n}
        """
        for handle in list(self._handles.values()) + list(
                self._skip_handles.values()):
            handle.close()
        buckets = set(self._counts) | set(self._skipped)
        return {container: {"keys": self._counts.get(container, 0),
                            "skipped_large": self._skipped.get(container, 0)}
                for container in buckets}
