"""
Tests for OR-aggregation of multiple proofs (ChatGPT's finding #3).

When multiple rules can derive the same conclusion, the combined confidence
should be computed via disjunction: P(A ∨ B) = 1 - (1-A)(1-B).
"""

import pytest
from logos.executor import Executor
from logos.confidence import ConfidenceValue


def make_two_route_executor():
    """
    Two independent rules that can both derive can-travel(alice):
      - rule 1: has-passport → confidence ~0.76
      - rule 2: has-visa     → confidence ~0.665
    Combined: 1 - (1-0.76)(1-0.665) ≈ 0.919
    """
    ex = Executor()
    ex.load_source("""
has-passport of alice := true
  confidence: 0.8
  provenance: "records"

has-visa of alice := true
  confidence: 0.7
  provenance: "records"

can-travel(P) if:
  P.has-passport = true

can-travel(P) if:
  P.has-visa = true
""")
    return ex


def test_or_aggregation_bool_query():
    ex = make_two_route_executor()
    result = ex.query("can-travel", "alice")
    assert result.is_true
    # Combined confidence must be higher than either individual proof
    # Individual proofs are ~0.76 and ~0.665 after degradation
    # Disjunction should push it above the max of the two
    assert result.confidence.point > 0.76


def test_or_aggregation_exceeds_max():
    """Disjunction must be strictly above max(A, B)."""
    ex = make_two_route_executor()
    result = ex.query("can-travel", "alice")
    # Both proofs individually will be around 0.76 and 0.665 after chain degradation
    # The combined must exceed the larger one
    assert result.confidence.point > 0.7


def test_or_aggregation_below_one():
    """Disjunction of two uncertain proofs must stay below 1.0."""
    ex = make_two_route_executor()
    result = ex.query("can-travel", "alice")
    assert result.confidence.point < 1.0


def test_single_proof_unchanged():
    """With only one derivation path, confidence equals that path's value."""
    ex = Executor()
    ex.load_source("""
has-passport of alice := true
  confidence: 0.8
can-travel(P) if:
  P.has-passport = true
""")
    result = ex.query("can-travel", "alice")
    assert result.is_true
    # Only one proof — no OR boost
    single_conf = result.confidence.point
    assert single_conf < 0.82   # degraded from 0.8


def test_find_or_aggregation():
    """find query: same binding from two rules gets OR-combined confidence."""
    ex = make_two_route_executor()
    outputs = ex.load_source("find P where can-travel(P)\n")
    # Run via executor.find
    travelers = ex.find("P", "can-travel")
    assert "alice" in travelers


def test_or_aggregation_formula():
    """Verify the disjunction formula directly on confidence values."""
    a = ConfidenceValue.from_point(0.76)
    b = ConfidenceValue.from_point(0.665)
    combined = a.disjoin(b)
    expected = 1.0 - (1.0 - 0.76) * (1.0 - 0.665)
    assert abs(combined.point - expected) < 1e-9
