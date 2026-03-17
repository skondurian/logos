"""
Confidence arithmetic for Logos.

Every value in Logos carries a ConfidenceValue. This module defines the
arithmetic over those values: conjunction (AND), disjunction (OR),
inference-chain degradation, and fallback-chain resolution.

Distribution model: Beta(alpha, beta) for uncertain values; Dirac(1.0)
for "absolute" confidence.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.stats import beta as beta_dist


# How much each inference step degrades confidence (multiplicative).
DEFAULT_DEGRADATION = 0.95


@dataclass
class ConfidenceValue:
    """A probability distribution over [0, 1].

    The canonical representation is a point estimate plus a 95% credible
    interval, with a named distribution for sampling/updating.

    Invariants:
        0.0 <= lower <= point <= upper <= 1.0
    """
    point: float          # MAP estimate
    lower: float          # 95% CI lower bound
    upper: float          # 95% CI upper bound
    distribution: str     # "beta", "gaussian", "dirac"
    # Beta distribution parameters (only meaningful when distribution="beta")
    alpha: float = field(default=1.0)
    beta_param: float = field(default=1.0)

    def __post_init__(self):
        self.point = float(np.clip(self.point, 0.0, 1.0))
        self.lower = float(np.clip(self.lower, 0.0, self.point))
        self.upper = float(np.clip(self.upper, self.point, 1.0))

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def absolute(cls) -> "ConfidenceValue":
        """Dirac delta at 1.0 — certainty."""
        return cls(point=1.0, lower=1.0, upper=1.0, distribution="dirac",
                   alpha=1e9, beta_param=1e-9)

    @classmethod
    def impossible(cls) -> "ConfidenceValue":
        """Dirac delta at 0.0 — logical impossibility."""
        return cls(point=0.0, lower=0.0, upper=0.0, distribution="dirac",
                   alpha=1e-9, beta_param=1e9)

    @classmethod
    def from_point(cls, p: float) -> "ConfidenceValue":
        """Beta distribution parameterized to have mode at p, weak prior."""
        p = float(np.clip(p, 1e-9, 1.0 - 1e-9))
        # Mode of Beta(a, b) = (a-1)/(a+b-2); solve with total concentration=20
        concentration = 20.0
        a = p * (concentration - 2) + 1
        b = concentration - a
        lo, hi = beta_dist.interval(0.95, a, b)
        return cls(point=p, lower=float(lo), upper=float(hi),
                   distribution="beta", alpha=a, beta_param=b)

    @classmethod
    def from_interval(cls, lower: float, upper: float) -> "ConfidenceValue":
        """Beta distribution fitted to a 95% credible interval."""
        point = (lower + upper) / 2
        p = float(np.clip(point, 1e-9, 1.0 - 1e-9))
        # Rough fit: use method of moments
        mean = p
        var = ((upper - lower) / 4) ** 2  # 95% CI ≈ mean ± 2σ
        var = max(var, 1e-8)
        a = mean * (mean * (1 - mean) / var - 1)
        b = (1 - mean) * (mean * (1 - mean) / var - 1)
        a = max(a, 0.1)
        b = max(b, 0.1)
        lo, hi = beta_dist.interval(0.95, a, b)
        return cls(point=p, lower=float(lo), upper=float(hi),
                   distribution="beta", alpha=a, beta_param=b)

    # ── Arithmetic ────────────────────────────────────────────────────────────

    def conjoin(self, other: "ConfidenceValue") -> "ConfidenceValue":
        """AND: P(A ∧ B) = P(A) × P(B) (assuming independence)."""
        p = self.point * other.point
        lo = self.lower * other.lower
        hi = self.upper * other.upper
        return ConfidenceValue.from_point(p)._with_interval(lo, hi)

    def disjoin(self, other: "ConfidenceValue") -> "ConfidenceValue":
        """OR: P(A ∨ B) = 1 - (1-A)(1-B) (assuming independence)."""
        p = 1.0 - (1.0 - self.point) * (1.0 - other.point)
        lo = 1.0 - (1.0 - self.lower) * (1.0 - other.lower)
        hi = 1.0 - (1.0 - self.upper) * (1.0 - other.upper)
        return ConfidenceValue.from_point(p)._with_interval(lo, hi)

    def degrade(self, factor: float = DEFAULT_DEGRADATION) -> "ConfidenceValue":
        """Inference-chain degradation: multiply by factor < 1."""
        factor = float(np.clip(factor, 0.0, 1.0))
        return ConfidenceValue.from_point(self.point * factor)._with_interval(
            self.lower * factor, self.upper * factor
        )

    def _with_interval(self, lo: float, hi: float) -> "ConfidenceValue":
        lo = float(np.clip(lo, 0.0, self.point))
        hi = float(np.clip(hi, self.point, 1.0))
        self.lower = lo
        self.upper = hi
        return self

    # ── Comparisons ───────────────────────────────────────────────────────────

    def __ge__(self, threshold: float) -> bool:
        return self.point >= threshold

    def __gt__(self, threshold: float) -> bool:
        return self.point > threshold

    def __le__(self, threshold: float) -> bool:
        return self.point <= threshold

    def __lt__(self, threshold: float) -> bool:
        return self.point < threshold

    def is_certain(self) -> bool:
        return self.point >= 1.0 - 1e-9

    def is_impossible(self) -> bool:
        return self.point <= 1e-9

    # ── Representation ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        if self.is_certain():
            return "confidence(absolute)"
        if self.is_impossible():
            return "confidence(impossible)"
        return (f"confidence({self.point:.3f} "
                f"[{self.lower:.3f}, {self.upper:.3f}] {self.distribution})")


def conjoin_all(values: list[ConfidenceValue]) -> ConfidenceValue:
    """Reduce a list by conjunction (AND of all)."""
    if not values:
        return ConfidenceValue.absolute()
    result = values[0]
    for v in values[1:]:
        result = result.conjoin(v)
    return result


def disjoin_all(values: list[ConfidenceValue]) -> ConfidenceValue:
    """Reduce a list by disjunction (OR of all)."""
    if not values:
        return ConfidenceValue.impossible()
    result = values[0]
    for v in values[1:]:
        result = result.disjoin(v)
    return result


def resolve_fallback_chain(
    primary: Optional[ConfidenceValue],
    fallbacks: list[tuple[Optional[ConfidenceValue], float]]
) -> tuple[int, ConfidenceValue]:
    """
    Resolve a fallback chain: use the first available value whose confidence
    meets or exceeds the annotated threshold.

    Returns (index, confidence) where index 0 = primary.
    """
    if primary is not None and not primary.is_impossible():
        return 0, primary
    for i, (cv, threshold) in enumerate(fallbacks):
        if cv is not None and cv.point >= threshold:
            # Annotate with the declared fallback confidence
            return i + 1, ConfidenceValue.from_point(threshold)
    # Last resort: return last fallback at its threshold
    if fallbacks:
        _, threshold = fallbacks[-1]
        return len(fallbacks), ConfidenceValue.from_point(threshold)
    return -1, ConfidenceValue.impossible()


def from_annotation(raw) -> ConfidenceValue:
    """Convert a raw AST confidence annotation to a ConfidenceValue."""
    if raw == "absolute":
        return ConfidenceValue.absolute()
    if isinstance(raw, (int, float)):
        return ConfidenceValue.from_point(float(raw))
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return ConfidenceValue.from_interval(float(raw[0]), float(raw[1]))
    raise ValueError(f"Unknown confidence annotation: {raw!r}")
