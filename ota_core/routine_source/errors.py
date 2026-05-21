from __future__ import annotations


class RoutineSourceError(Exception):
    pass


class ManifestNotFoundError(RoutineSourceError):
    pass


class RoutineBundleError(RoutineSourceError):
    pass


class FileIntegrityError(RoutineBundleError):
    def __init__(self, path: str, expected: str, actual: str) -> None:
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"sha256 mismatch for {path}: declared {expected[:12]}..., actual {actual[:12]}..."
        )


class DuplicateRoutineError(RoutineSourceError):
    def __init__(self, routine_id: str, paths: list[str]) -> None:
        self.routine_id = routine_id
        self.paths = paths
        super().__init__(f"duplicate routine id {routine_id} in: {paths}")
