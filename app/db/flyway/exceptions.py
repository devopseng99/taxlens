"""Flyway migration exceptions."""


class FlywayError(Exception):
    """Base exception for migration errors."""
    pass


class ChecksumMismatchError(FlywayError):
    """Raised when an applied migration's file has been modified."""

    def __init__(self, version: int, expected: str, actual: str):
        self.version = version
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"V{version:03d} checksum mismatch: "
            f"expected {expected[:12]}... got {actual[:12]}..."
        )


class MigrationFailedError(FlywayError):
    """Raised when a migration SQL execution fails."""

    def __init__(self, version: int, cause: str):
        self.version = version
        super().__init__(f"V{version:03d} failed: {cause}")
