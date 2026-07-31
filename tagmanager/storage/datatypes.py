"""
Purpose: Coarse data-type classification from an object key's extension —
zero API cost, every backend, a greppable constant map. The optimizer
learns WHAT the data is (logs / media / archives / data / docs / other),
not just how old, so recommendations can suggest type-zoned layouts.
Author(s): John Reed
"""

# Constants

DEFAULT_TYPE = "other"

# Extension (lower-case, no leading dot) -> coarse type. Compound
# extensions resolve to the OUTERMOST meaningful one (e.g. .tar.gz ->
# archives), so archive suffixes are checked before the inner data ones.
EXTENSION_MAP = {
    # logs
    "log": "logs", "log.gz": "logs", "ndjson": "logs", "audit": "logs",
    # media
    "jpg": "media", "jpeg": "media", "png": "media", "gif": "media",
    "webp": "media", "svg": "media", "mp4": "media", "mov": "media",
    "avi": "media", "mkv": "media", "mp3": "media", "wav": "media",
    "flac": "media", "heic": "media", "tiff": "media",
    # archives (checked before data suffixes for compound extensions)
    "tar": "archives", "tar.gz": "archives", "tgz": "archives",
    "tar.bz2": "archives", "tar.zst": "archives", "zip": "archives",
    "gz": "archives", "bz2": "archives", "zst": "archives", "7z": "archives",
    "rar": "archives", "xz": "archives", "backup": "archives",
    "bak": "archives", "snapshot": "archives",
    # data
    "csv": "data", "tsv": "data", "json": "data", "parquet": "data",
    "avro": "data", "orc": "data", "db": "data", "sqlite": "data",
    "sql": "data", "xml": "data", "arrow": "data", "feather": "data",
    "pkl": "data", "npy": "data", "npz": "data",
    # docs
    "pdf": "docs", "doc": "docs", "docx": "docs", "xls": "docs",
    "xlsx": "docs", "ppt": "docs", "pptx": "docs", "txt": "docs",
    "md": "docs", "rtf": "docs", "odt": "docs",
}

# Compound suffixes to try before the final-segment lookup, longest first.
_COMPOUND = tuple(sorted(
    (ext for ext in EXTENSION_MAP if "." in ext),
    key=lambda ext: -ext.count(".")))


def classify_key(key):
    """
    Coarse data type for an object key from its extension.

    Compound extensions win over their inner segment (`.tar.gz` ->
    archives, not the `.gz` alone would give — same here, but e.g. a
    hypothetical `.csv.gz` resolves to the archive, matching how the
    object is actually stored). Matching is case-insensitive; a key with
    no extension (or an unknown one) is `other`.

    :param key: object key / path
    :returns: one of logs/media/archives/data/docs/other
    """
    name = key.rsplit("/", 1)[-1].lower()
    if "." not in name:
        return DEFAULT_TYPE

    for suffix in _COMPOUND:
        if name.endswith("." + suffix):
            return EXTENSION_MAP[suffix]

    ext = name.rsplit(".", 1)[-1]
    return EXTENSION_MAP.get(ext, DEFAULT_TYPE)
