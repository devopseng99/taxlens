"""SHA-256 file hashing for migration integrity checks."""

import hashlib


def file_checksum(filepath: str) -> str:
    """Compute SHA-256 checksum of a migration file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
