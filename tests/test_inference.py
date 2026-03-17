"""Tests for the inference engine."""

import pytest
from logos.inference import InferenceEngine, Proof, unify_term, walk
from logos.semantic_graph import SemanticGraph, FactNode
from logos.confidence import ConfidenceValue
from logos.ast_nodes import (
    InferenceRule, PredicateCall, Comparison, NegatedPredicate,
    Variable, Path, DurationLit
)


def make_engine(facts=None, rules=None):
    graph = SemanticGraph()
    for f in (facts or []):
        graph.assert_fact(f)
    engine = InferenceEngine(graph=graph, rules=rules or [])
    return engine, graph


def fact(subject, predicate, value, confidence=1.0):
    conf = ConfidenceValue.absolute() if confidence == 1.0 else ConfidenceValue.from_point(confidence)
    return FactNode.make(subject, predicate, value, confidence=conf)


# ─── Unification ──────────────────────────────────────────────────────────────

def test_unify_equal_literals():
    assert unify_term(42, 42, {}) == {}

def test_unify_different_literals():
    assert unify_term(1, 2, {}) is None

def test_unify_variable_to_value():
    result = unify_term(Variable("X"), 42, {})
    assert result == {"X": 42}

def test_unify_value_to_variable():
    result = unify_term(42, Variable("X"), {})
    assert result == {"X": 42}

def test_unify_two_variables():
    result = unify_term(Variable("X"), Variable("Y"), {})
    assert result is not None

def test_walk_chain():
    bindings = {"X": Variable("Y"), "Y": 42}
    assert walk(Variable("X"), bindings) == 42


# ─── Fact lookup ──────────────────────────────────────────────────────────────

def test_prove_fact_present():
    engine, _ = make_engine(facts=[fact("alice", "age", DurationLit(30, "years"))])
    pred = PredicateCall(name="age", args=[Path(parts=["alice"])])
    proof = engine.prove_first(pred)
    assert proof.success

def test_prove_fact_absent():
    engine, _ = make_engine()
    pred = PredicateCall(name="age", args=[Path(parts=["alice"])])
    proof = engine.prove_first(pred)
    assert not proof.success


# ─── Rule-based inference ─────────────────────────────────────────────────────

def test_simple_rule():
    """can-vote(P) if P.age >= 18 years and P.citizenship = "US"."""
    rule = InferenceRule(
        head=PredicateCall(name="can-vote", args=[Variable("P")]),
        conditions=[
            Comparison(left=Path(parts=["P", "age"]), op=">=",
                       right=DurationLit(18, "years")),
            Comparison(left=Path(parts=["P", "citizenship"]), op="=",
                       right="US"),
        ]
    )
    facts = [
        fact("alice", "age", DurationLit(30, "years")),
        fact("alice", "citizenship", "US"),
    ]
    engine, _ = make_engine(facts=facts, rules=[rule])
    pred = PredicateCall(name="can-vote", args=[Path(parts=["alice"])])
    proof = engine.prove_first(pred)
    assert proof.success

def test_rule_fails_condition():
    """Bob is 17 — cannot vote."""
    rule = InferenceRule(
        head=PredicateCall(name="can-vote", args=[Variable("P")]),
        conditions=[
            Comparison(left=Path(parts=["P", "age"]), op=">=",
                       right=DurationLit(18, "years")),
        ]
    )
    facts = [fact("bob", "age", DurationLit(17, "years"))]
    engine, _ = make_engine(facts=facts, rules=[rule])
    pred = PredicateCall(name="can-vote", args=[Path(parts=["bob"])])
    proof = engine.prove_first(pred)
    assert not proof.success


# ─── Confidence propagation ───────────────────────────────────────────────────

def test_confidence_degrades():
    rule = InferenceRule(
        head=PredicateCall(name="derived", args=[Variable("P")]),
        conditions=[
            Comparison(left=Path(parts=["P", "score"]), op=">=", right=0.5),
        ]
    )
    facts = [fact("alice", "score", 0.9)]
    engine, _ = make_engine(facts=facts, rules=[rule])
    pred = PredicateCall(name="derived", args=[Path(parts=["alice"])])
    proof = engine.prove_first(pred)
    assert proof.success
    # Confidence should be degraded
    assert proof.confidence.point < 1.0

def test_confidence_conjunction_le_min():
    rule = InferenceRule(
        head=PredicateCall(name="both", args=[Variable("P")]),
        conditions=[
            Comparison(left=Path(parts=["P", "a"]), op=">=", right=0.0),
            Comparison(left=Path(parts=["P", "b"]), op=">=", right=0.0),
        ]
    )
    facts = [
        fact("alice", "a", 0.8, confidence=0.8),
        fact("alice", "b", 0.6, confidence=0.6),
    ]
    engine, _ = make_engine(facts=facts, rules=[rule])
    pred = PredicateCall(name="both", args=[Path(parts=["alice"])])
    proof = engine.prove_first(pred)
    assert proof.success
    assert proof.confidence.point <= 0.8


# ─── Negation as failure ──────────────────────────────────────────────────────

def test_negation_succeeds_when_absent():
    engine, _ = make_engine()
    neg = NegatedPredicate(predicate=PredicateCall(
        name="has-record", args=[Path(parts=["alice"])]
    ))
    proof = engine.prove_first(neg)
    assert proof.success

def test_negation_fails_when_present():
    facts = [fact("alice", "has-record", True)]
    rule = InferenceRule(
        head=PredicateCall(name="has-record", args=[Variable("P")]),
        conditions=[
            Comparison(left=Path(parts=["P", "has-record"]), op="=", right=True)
        ]
    )
    engine, _ = make_engine(facts=facts, rules=[rule])
    neg = NegatedPredicate(predicate=PredicateCall(
        name="has-record", args=[Path(parts=["alice"])]
    ))
    proof = engine.prove_first(neg)
    assert not proof.success


# ─── Find queries ─────────────────────────────────────────────────────────────

def test_find_all_voters():
    rule = InferenceRule(
        head=PredicateCall(name="can-vote", args=[Variable("P")]),
        conditions=[
            Comparison(left=Path(parts=["P", "age"]), op=">=",
                       right=DurationLit(18, "years")),
        ]
    )
    facts = [
        fact("alice", "age", DurationLit(30, "years")),
        fact("bob", "age", DurationLit(17, "years")),
        fact("carol", "age", DurationLit(22, "years")),
    ]
    engine, graph = make_engine(facts=facts, rules=[rule])
    goal = PredicateCall(name="can-vote", args=[Variable("P")])
    proofs = list(engine.prove(goal))
    subjects = {p.bindings.get("P") for p in proofs if p.success}
    assert "alice" in subjects
    assert "carol" in subjects
    assert "bob" not in subjects
