"""Integration tests for the Executor pipeline."""

import pathlib
import pytest

from logos.executor import Executor, run_file, run_source
from logos.confidence import ConfidenceValue


EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


# ─── Basic fact round-trip ────────────────────────────────────────────────────

def test_assert_and_query_fact():
    ex = run_source("""
name of alice := "Alice"
  confidence: absolute
  provenance: "test"
""")
    result = ex.graph.query("alice", "name")
    assert result.found
    assert result.value == "Alice"
    assert result.confidence.is_certain()

def test_duration_fact():
    ex = run_source("age of alice := 30 years\n  confidence: absolute\n")
    from logos.ast_nodes import DurationLit
    result = ex.graph.query("alice", "age")
    assert result.found
    assert isinstance(result.value, DurationLit)
    assert result.value.amount == 30

def test_retraction():
    ex = run_source("""
age of alice := 30 years
  confidence: absolute
retract: age of alice
""")
    result = ex.graph.query("alice", "age")
    assert not result.found


# ─── Inference ────────────────────────────────────────────────────────────────

def test_voting_example():
    ex = Executor()
    ex.load_source("""
age of alice := 30 years
  confidence: absolute
citizenship of alice := "US"
  confidence: absolute
age of bob := 17 years
  confidence: absolute
citizenship of bob := "US"
  confidence: absolute
can-vote(P) if:
  P.age >= 18 years
  P.citizenship = "US"
""")

    alice_result = ex.query("can-vote", "alice")
    assert alice_result.is_true
    # Confidence is degraded by one rule-chain step
    assert alice_result.confidence.point > 0.9

    bob_result = ex.query("can-vote", "bob")
    assert not bob_result.is_true

    voters = ex.find("P", "can-vote")
    assert "alice" in voters
    assert "bob" not in voters


# ─── Example file loading ─────────────────────────────────────────────────────

def test_load_hello_facts():
    ex = run_file(str(EXAMPLES / "01_hello_facts.logos"))
    assert ex.graph.query("alice", "name").found
    assert ex.graph.query("alice", "age").found

def test_load_voting_rules():
    ex = run_file(str(EXAMPLES / "02_voting_rules.logos"))
    assert ex.graph.query("alice", "age").found
    alice = ex.query("can-vote", "alice")
    assert alice.is_true

def test_load_uncertain_location():
    ex = run_file(str(EXAMPLES / "03_uncertain_location.logos"))
    assert ex.graph.query("device", "location").found

def test_load_recommendation():
    ex = run_file(str(EXAMPLES / "04_recommendation.logos"))
    assert "recommend" in ex.transforms

def test_load_contexts():
    ex = run_file(str(EXAMPLES / "05_contexts.logos"))
    assert ex.context_registry.get("Production") is not None
    assert ex.context_registry.get("Development") is not None


# ─── Confidence propagation through rules ────────────────────────────────────

def test_uncertain_facts_propagate():
    ex = Executor()
    ex.load_source("""
score of alice := 0.8
  confidence: 0.8
high-score(P) if:
  P.score >= 0.5
""")
    result = ex.query("high-score", "alice")
    assert result.is_true
    # Confidence should be degraded by rule chain
    assert 0.0 < result.confidence.point <= 0.8


# ─── Type checking ────────────────────────────────────────────────────────────

def test_type_registered():
    ex = run_source("Person:\n  name: HumanName\n  age: Duration\n")
    assert ex.type_lattice.exists("Person")
    assert ex.type_lattice.is_subtype_of("Person", "Entity")


# ─── Contradiction handling ───────────────────────────────────────────────────

def test_contradiction_warning():
    import warnings
    from logos.errors import ContradictionWarning
    ex = Executor()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        ex.load_source("""
age of alice := 30 years
  confidence: absolute
age of alice := 31 years
  confidence: absolute
""")
        contradiction_warnings = [x for x in w if issubclass(x.category, ContradictionWarning)]
        assert len(contradiction_warnings) >= 1

def test_contradiction_both_retained():
    import warnings
    from logos.errors import ContradictionWarning
    ex = Executor()
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        ex.load_source("""
age of alice := 30 years
  confidence: absolute
age of alice := 31 years
  confidence: absolute
""")
    result = ex.graph.query("alice", "age")
    # Both facts retained; query returns the highest-confidence one
    assert result.found
    key = ("alice", "age")
    from logos.ast_nodes import DurationLit
    ids = ex.graph._index.get(key, [])
    assert len(ids) == 2
