"""Tests for the Logos parser."""

import pytest
from logos.parser import parse
from logos.ast_nodes import (
    Program, TypeDecl, SemanticBinding, InferenceRule, BoolQuery, FindQuery,
    ContextDecl, TransformDecl, Retraction, DurationLit, Path, Variable,
    PredicateCall, Comparison,
)


def parse_stmts(source: str):
    return parse(source).statements


# ─── Type declarations ────────────────────────────────────────────────────────

def test_parse_simple_type():
    stmts = parse_stmts("Person:\n  name: HumanName\n  age: Duration\n")
    assert len(stmts) == 1
    assert isinstance(stmts[0], TypeDecl)
    assert stmts[0].name == "Person"
    assert len(stmts[0].fields) == 2
    assert stmts[0].fields[0].name == "name"

def test_parse_type_with_parents():
    stmts = parse_stmts("Employee (Person):\n  company: Text\n")
    assert isinstance(stmts[0], TypeDecl)
    assert "Person" in stmts[0].parents

def test_parse_type_no_fields():
    stmts = parse_stmts("Animal (Entity):\n")
    # Either parsed or gracefully skipped; no crash
    assert isinstance(stmts[0], TypeDecl)


# ─── Semantic bindings ────────────────────────────────────────────────────────

def test_parse_simple_binding():
    stmts = parse_stmts('name of alice := "Alice"\n')
    assert len(stmts) == 1
    b = stmts[0]
    assert isinstance(b, SemanticBinding)
    assert b.path.parts == ["alice", "name"]
    assert b.value == "Alice"

def test_parse_duration_binding():
    stmts = parse_stmts("age of alice := 30 years\n")
    b = stmts[0]
    assert isinstance(b, SemanticBinding)
    assert isinstance(b.value, DurationLit)
    assert b.value.amount == 30
    assert b.value.unit == "years"

def test_parse_binding_with_confidence():
    src = "age of alice := 30 years\n  confidence: absolute\n"
    stmts = parse_stmts(src)
    b = stmts[0]
    assert isinstance(b, SemanticBinding)
    assert b.annotations.confidence is not None
    assert b.annotations.confidence.raw == "absolute"

def test_parse_binding_with_provenance():
    src = 'age of alice := 30 years\n  confidence: absolute\n  provenance: "birth-record"\n'
    stmts = parse_stmts(src)
    b = stmts[0]
    assert b.annotations.provenance is not None
    assert b.annotations.provenance.source == "birth-record"

def test_parse_binding_numeric_confidence():
    src = "score of alice := 0.9\n  confidence: 0.8\n"
    stmts = parse_stmts(src)
    b = stmts[0]
    assert abs(b.annotations.confidence.raw - 0.8) < 1e-6


# ─── Retraction ───────────────────────────────────────────────────────────────

def test_parse_retraction():
    stmts = parse_stmts("retract: age of alice\n")
    assert isinstance(stmts[0], Retraction)
    assert stmts[0].path.parts == ["alice", "age"]


# ─── Inference rules ──────────────────────────────────────────────────────────

def test_parse_rule():
    src = "can-vote(P) if:\n  P.age >= 18 years\n  P.citizenship = \"US\"\n"
    stmts = parse_stmts(src)
    assert len(stmts) == 1
    rule = stmts[0]
    assert isinstance(rule, InferenceRule)
    assert rule.head.name == "can-vote"
    assert len(rule.head.args) == 1
    assert isinstance(rule.head.args[0], Variable)
    assert rule.head.args[0].name == "P"
    assert len(rule.conditions) == 2

def test_parse_rule_conditions():
    src = "eligible(P) if:\n  P.age >= 18 years\n"
    stmts = parse_stmts(src)
    rule = stmts[0]
    cond = rule.conditions[0]
    assert isinstance(cond, Comparison)
    assert cond.op == ">="
    assert isinstance(cond.right, DurationLit)


# ─── Queries ──────────────────────────────────────────────────────────────────

def test_parse_bool_query():
    stmts = parse_stmts("query: can-vote(alice)?\n")
    assert isinstance(stmts[0], BoolQuery)
    assert stmts[0].predicate.name == "can-vote"

def test_parse_find_query():
    stmts = parse_stmts("find P where can-vote(P)\n")
    assert isinstance(stmts[0], FindQuery)
    assert len(stmts[0].variables) == 1
    assert stmts[0].variables[0].name == "P"


# ─── Contexts ─────────────────────────────────────────────────────────────────

def test_parse_context():
    src = "context Production:\n  confidence-threshold: 0.99\n  error-tolerance: zero\n"
    stmts = parse_stmts(src)
    assert isinstance(stmts[0], ContextDecl)
    assert stmts[0].name == "Production"
    assert len(stmts[0].directives) == 2


# ─── Full example files ───────────────────────────────────────────────────────

def test_parse_hello_facts(examples_dir):
    from logos.parser import parse_file
    prog = parse_file(str(examples_dir / "01_hello_facts.logos"))
    assert len(prog.statements) > 0

def test_parse_voting_rules(examples_dir):
    from logos.parser import parse_file
    prog = parse_file(str(examples_dir / "02_voting_rules.logos"))
    # Should have type decl, facts, rule, and queries
    types = [s for s in prog.statements if isinstance(s, TypeDecl)]
    rules = [s for s in prog.statements if isinstance(s, InferenceRule)]
    queries = [s for s in prog.statements if isinstance(s, (BoolQuery, FindQuery))]
    assert len(types) >= 1
    assert len(rules) >= 1
    assert len(queries) >= 1


# ─── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def examples_dir():
    import pathlib
    return pathlib.Path(__file__).parent.parent / "examples"
