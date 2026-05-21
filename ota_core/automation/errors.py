from __future__ import annotations


class AutomationError(Exception):
    pass


class DuplicateJobError(AutomationError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"job already registered: {job_id}")


class UnknownJobError(AutomationError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"unknown job: {job_id}")
