"""
Context system for Logos.

Contexts partition the semantic graph and control:
  - confidence thresholds for queries
  - error tolerance levels
  - inheritance from parent contexts
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from logos.ast_nodes import ContextDecl, ContextDirective
from logos import errors as err


# ─── Error tolerance levels ───────────────────────────────────────────────────

ERROR_TOLERANCE = {
    "zero":   0.0,
    "low":    0.1,
    "medium": 0.3,
    "high":   0.7,
}


# ─── Context definition ───────────────────────────────────────────────────────

@dataclass
class Context:
    name: str
    confidence_threshold: float = 0.0
    error_tolerance: float = 0.3       # medium
    extends: Optional[str] = None      # parent context name

    @classmethod
    def from_decl(cls, decl: ContextDecl) -> "Context":
        ctx = cls(name=decl.name)
        for d in decl.directives:
            if d.kind == "confidence-threshold":
                ctx.confidence_threshold = float(d.value)
            elif d.kind == "error-tolerance":
                if d.value not in ERROR_TOLERANCE:
                    raise err.ContextError(
                        f"Unknown error-tolerance level: {d.value!r}"
                    )
                ctx.error_tolerance = ERROR_TOLERANCE[d.value]
            elif d.kind == "extends":
                ctx.extends = str(d.value)
        return ctx


# ─── Context registry ─────────────────────────────────────────────────────────

class ContextRegistry:
    """
    Registry of all declared contexts.

    The default context has threshold 0.0 and medium error tolerance.
    """

    DEFAULT_NAME = "__default__"

    def __init__(self):
        self._contexts: dict[str, Context] = {
            self.DEFAULT_NAME: Context(name=self.DEFAULT_NAME),
        }
        self._active: list[str] = [self.DEFAULT_NAME]

    def register(self, ctx: Context):
        if ctx.extends and ctx.extends not in self._contexts:
            raise err.ContextError(
                f"Context '{ctx.name}' extends unknown context '{ctx.extends}'"
            )
        self._contexts[ctx.name] = ctx

    def activate(self, name: str):
        if name not in self._contexts:
            raise err.ContextError(f"Unknown context: {name!r}")
        if name not in self._active:
            self._active.append(name)

    def deactivate(self, name: str):
        if name in self._active and name != self.DEFAULT_NAME:
            self._active.remove(name)

    def get(self, name: str) -> Optional[Context]:
        return self._contexts.get(name)

    def effective_threshold(self, context_name: Optional[str] = None) -> float:
        """
        Return the effective confidence threshold for a given context name,
        resolving inheritance.
        """
        name = context_name or self.DEFAULT_NAME
        visited = set()
        threshold = 0.0
        while name and name not in visited:
            visited.add(name)
            ctx = self._contexts.get(name)
            if ctx is None:
                break
            threshold = max(threshold, ctx.confidence_threshold)
            name = ctx.extends
        return threshold

    def effective_tolerance(self, context_name: Optional[str] = None) -> float:
        name = context_name or self.DEFAULT_NAME
        ctx = self._contexts.get(name)
        if ctx is None:
            return ERROR_TOLERANCE["medium"]
        if ctx.extends:
            parent = self._contexts.get(ctx.extends)
            if parent:
                return min(ctx.error_tolerance, parent.error_tolerance)
        return ctx.error_tolerance

    def active_context_names(self) -> list[str]:
        return list(self._active)

    def all_context_names(self) -> list[str]:
        return list(self._contexts.keys())
