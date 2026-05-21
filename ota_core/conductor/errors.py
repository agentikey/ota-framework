from __future__ import annotations


class ConductorError(Exception):
    pass


class NoRouteError(ConductorError):
    def __init__(self, intent_summary: str) -> None:
        self.intent_summary = intent_summary
        super().__init__(f"no route for intent: {intent_summary}")


class RoutineNotRegisteredError(ConductorError):
    def __init__(self, routine_id: str) -> None:
        self.routine_id = routine_id
        super().__init__(f"routine not registered with conductor: {routine_id}")
