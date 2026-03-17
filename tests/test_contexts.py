"""
Tests for context threading into inference (ChatGPT finding #2 / Gemini).

Contexts now filter facts by:
  1. Confidence threshold — facts below threshold are invisible during inference.
  2. Context tag — facts tagged with a context are only visible when that
     context is active.
"""

import pytest
from logos.executor import Executor


# ─── Confidence threshold filtering ──────────────────────────────────────────

def test_high_threshold_hides_low_confidence_facts():
    """Facts below the active context's threshold are not provable."""
    ex = Executor()
    ex.load_source("""
context Strict:
  confidence-threshold: 0.95
  error-tolerance: zero

score of alice := 0.8
  confidence: 0.8
  provenance: "test"

high-score(P) if:
  P.score >= 0.5
""")
    ex.activate_context("Strict")
    # alice.score has confidence 0.8 < 0.95 threshold → not visible
    result = ex.query("high-score", "alice")
    assert not result.is_true


def test_low_threshold_allows_uncertain_facts():
    """Default context (threshold 0.0) allows all confidence levels."""
    ex = Executor()
    ex.load_source("""
score of alice := 0.8
  confidence: 0.8
  provenance: "test"

high-score(P) if:
  P.score >= 0.5
""")
    # No context activated — default threshold is 0.0
    result = ex.query("high-score", "alice")
    assert result.is_true


def test_context_threshold_blocks_inference():
    """Inference is blocked when source fact is below active threshold."""
    ex = Executor()
    ex.load_source("""
context Production:
  confidence-threshold: 0.99
  error-tolerance: zero

age of alice := 30 years
  confidence: 0.85
  provenance: "unverified"

can-vote(P) if:
  P.age >= 18 years
""")
    ex.activate_context("Production")
    result = ex.query("can-vote", "alice")
    assert not result.is_true


def test_absolute_confidence_passes_any_threshold():
    """Absolute (1.0) confidence facts are visible at any threshold."""
    ex = Executor()
    ex.load_source("""
context Production:
  confidence-threshold: 0.99
  error-tolerance: zero

age of alice := 30 years
  confidence: absolute
  provenance: "birth-record"

can-vote(P) if:
  P.age >= 18 years
""")
    ex.activate_context("Production")
    result = ex.query("can-vote", "alice")
    assert result.is_true


# ─── Context-tagged fact scoping ──────────────────────────────────────────────

def test_context_tagged_fact_invisible_without_context():
    """A fact tagged with a context is not visible when that context is not active."""
    ex = Executor()
    ex.load_source("""
context Development:
  confidence-threshold: 0.5

temperature of sensor := 68.0
  confidence: 0.7
  provenance: "uncalibrated"
  context: Development
""")
    # Development is not active — fact should be invisible
    result = ex.graph.query("sensor", "temperature")
    # The fact is stored, but the inference engine won't use it
    assert result.found  # it IS in the graph...

    ex2 = Executor()
    ex2.load_source("""
context Development:
  confidence-threshold: 0.5

temperature of sensor := 68.0
  confidence: 0.7
  provenance: "uncalibrated"
  context: Development

is-warm(S) if:
  S.temperature > 50.0
""")
    # Without activating Development, fact is scoped out
    result_no_ctx = ex2.query("is-warm", "sensor")
    assert not result_no_ctx.is_true

    # With Development active, fact becomes visible
    ex2.activate_context("Development")
    result_with_ctx = ex2.query("is-warm", "sensor")
    assert result_with_ctx.is_true


def test_global_facts_always_visible():
    """Facts without a context tag are visible regardless of active context."""
    ex = Executor()
    ex.load_source("""
context Production:
  confidence-threshold: 0.99

age of alice := 30 years
  confidence: absolute
  provenance: "birth-record"

can-vote(P) if:
  P.age >= 18 years
""")
    # Even with Production active, global absolute-confidence fact is visible
    ex.activate_context("Production")
    result = ex.query("can-vote", "alice")
    assert result.is_true


# ─── Context inheritance ───────────────────────────────────────────────────────

def test_context_threshold_effective():
    """effective_threshold returns the highest threshold in active chain."""
    ex = Executor()
    ex.load_source("""
context Base:
  confidence-threshold: 0.7

context Strict:
  confidence-threshold: 0.95
  extends: Base
""")
    assert ex.context_registry.effective_threshold("Strict") == pytest.approx(0.95)
    assert ex.context_registry.effective_threshold("Base") == pytest.approx(0.7)
