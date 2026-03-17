"""Logos error hierarchy."""


class LogosError(Exception):
    """Base for all Logos errors."""


class ParseError(LogosError):
    pass


class TypeError(LogosError):
    pass


class ConfidenceError(LogosError):
    pass


class InferenceError(LogosError):
    pass


class CycleDetectedError(InferenceError):
    """Raised when the inference engine detects a cyclic dependency."""
    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"Cycle detected in inference: {' → '.join(cycle)}")


class DepthLimitError(InferenceError):
    """Raised when inference exceeds the configured depth limit."""
    def __init__(self, depth: int):
        self.depth = depth
        super().__init__(f"Inference depth limit ({depth}) exceeded")


class UnificationError(InferenceError):
    """Raised when two terms cannot be unified."""
    def __init__(self, a, b):
        super().__init__(f"Cannot unify {a!r} with {b!r}")


class ContextError(LogosError):
    pass


class ExecutionError(LogosError):
    pass


class LogosImportError(LogosError):
    pass


class ContradictionWarning(UserWarning):
    """Issued (not raised) when contradictory facts are asserted.
    Both facts are retained with their provenance."""
