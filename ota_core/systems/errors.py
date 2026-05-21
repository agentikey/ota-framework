from __future__ import annotations


class RoutineEngineError(Exception):
    pass


class RoutineHelpersError(RoutineEngineError):
    pass


class KnobResolutionError(RoutineEngineError):
    pass


class RoutineRunError(RoutineEngineError):
    pass
