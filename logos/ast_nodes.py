"""
AST node definitions for Logos.

All nodes are pure dataclasses — no logic, no imports from other logos modules.
This is the interface contract between parser and all downstream consumers.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


# ─── Literals ─────────────────────────────────────────────────────────────────

@dataclass
class DurationLit:
    amount: float
    unit: str  # "years", "months", "days", "hours", "minutes", "seconds"

    def to_seconds(self) -> float:
        factors = {
            "years": 365.25 * 86400,
            "year": 365.25 * 86400,
            "months": 30.44 * 86400,
            "month": 30.44 * 86400,
            "days": 86400,
            "day": 86400,
            "hours": 3600,
            "hour": 3600,
            "minutes": 60,
            "minute": 60,
            "seconds": 1,
            "second": 1,
        }
        return self.amount * factors[self.unit]

    def __repr__(self) -> str:
        return f"{self.amount} {self.unit}"


@dataclass
class SetLit:
    elements: list[Any]


@dataclass
class ListLit:
    elements: list[Any]


# ─── Paths and atoms ──────────────────────────────────────────────────────────

@dataclass
class Path:
    """Dot-separated access path: alice.age or just alice."""
    parts: list[str]

    @staticmethod
    def of(subject: str, predicate: str) -> "Path":
        """Create path from 'predicate of subject' syntax."""
        return Path(parts=[subject, predicate])

    def __str__(self) -> str:
        return ".".join(self.parts)

    def root(self) -> str:
        return self.parts[0]

    def tail(self) -> Optional[str]:
        return self.parts[-1] if len(self.parts) > 1 else None


@dataclass
class Variable:
    """Unbound logical variable (uppercase in source)."""
    name: str

    def __str__(self) -> str:
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, Variable) and self.name == other.name


@dataclass
class ArithExpr:
    left: Any
    op: str
    right: Any


# ─── Confidence ───────────────────────────────────────────────────────────────

@dataclass
class ConfidenceAnnotation:
    """Raw confidence from source: 'absolute', a float, or [lower, upper]."""
    raw: Any  # "absolute" | float | (float, float)


@dataclass
class ProvenanceAnnotation:
    source: str


@dataclass
class Annotations:
    confidence: Optional[ConfidenceAnnotation] = None
    provenance: Optional[ProvenanceAnnotation] = None
    fallbacks: list["FallbackEntry"] = field(default_factory=list)
    context_name: Optional[str] = None


@dataclass
class FallbackEntry:
    path: Path
    confidence: Optional[float] = None


# ─── Type declarations ────────────────────────────────────────────────────────

@dataclass
class TypeExpr:
    name: str
    params: list["TypeExpr"] = field(default_factory=list)


@dataclass
class FieldDecl:
    name: str
    type_expr: TypeExpr


@dataclass
class TypeDecl:
    name: str
    parents: list[str] = field(default_factory=list)
    fields: list[FieldDecl] = field(default_factory=list)


# ─── Semantic bindings ────────────────────────────────────────────────────────

@dataclass
class SemanticBinding:
    path: Path
    value: Any
    annotations: Annotations = field(default_factory=Annotations)


@dataclass
class Retraction:
    path: Path


# ─── Inference rules ──────────────────────────────────────────────────────────

@dataclass
class PredicateCall:
    name: str
    args: list[Any]  # Path | Variable | literal


@dataclass
class Comparison:
    left: Any  # Path or variable
    op: str    # ">=", "<=", ">", "<", "=", "!="
    right: Any # value or variable


@dataclass
class NegatedPredicate:
    predicate: PredicateCall


Condition = PredicateCall | Comparison | NegatedPredicate


@dataclass
class InferenceRule:
    head: PredicateCall
    conditions: list[Condition]


# ─── Transforms ───────────────────────────────────────────────────────────────

@dataclass
class Param:
    name: str
    type_expr: TypeExpr


@dataclass
class TransformDirective:
    kind: str   # "intent", "considering", "maximize", "minimize", "require"
    value: Any


@dataclass
class TransformDecl:
    name: str
    params: list[Param]
    return_type: TypeExpr
    directives: list[TransformDirective]


# ─── Contexts ─────────────────────────────────────────────────────────────────

@dataclass
class ContextDirective:
    kind: str   # "confidence-threshold", "error-tolerance", "extends"
    value: Any


@dataclass
class ContextDecl:
    name: str
    directives: list[ContextDirective]


# ─── Queries ─────────────────────────────────────────────────────────────────

@dataclass
class BoolQuery:
    predicate: PredicateCall


@dataclass
class FindQuery:
    variables: list[Variable]
    conditions: list[Condition]
    confidence_filter: Optional[tuple[str, float]] = None  # (op, threshold)


# ─── Import ───────────────────────────────────────────────────────────────────

@dataclass
class ImportStmt:
    name: Optional[str]  # None means wildcard "*"
    source: str          # file path string


# ─── Program ─────────────────────────────────────────────────────────────────

Statement = (TypeDecl | SemanticBinding | Retraction | InferenceRule |
             TransformDecl | ContextDecl | BoolQuery | FindQuery | ImportStmt)


@dataclass
class Program:
    statements: list[Statement]
