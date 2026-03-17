"""
Phase F test: verify evaluator.logos correctly executes AST from parser.logos.

Exit criterion from roadmap:
    evaluator.logos can evaluate a simple .logos program (facts + one inference
    rule + one query) entirely as Logos inference.
"""
from __future__ import annotations
import io
import os
import sys
import pytest

from logos.executor import Executor
from logos.lexer import tokenize
from logos.ast_nodes import Variable, PredicateCall
from logos.inference import apply_bindings


PARSER_LOGOS = os.path.join(
    os.path.dirname(__file__), "..", "logos", "parser.logos"
)
EVALUATOR_LOGOS = os.path.join(
    os.path.dirname(__file__), "..", "logos", "evaluator.logos"
)


def run_logos_program(source: str, capture_output: bool = True) -> tuple[bool, str]:
    """
    Run a Logos program through the full Logos-in-Logos pipeline:
      tokenize → parse → evaluate
    Returns (success, captured_output).
    """
    ex = Executor()
    ex.load_file(PARSER_LOGOS)
    ex.load_file(EVALUATOR_LOGOS)

    toks = tokenize(source)
    tok_list = [[t.type, t.value] for t in toks]

    # Parse
    goal_parse = PredicateCall(name="parse-tokens", args=[tok_list, Variable("AST")])
    parse_results = list(ex.engine.prove_all([goal_parse]))
    parse_successes = [r for r in parse_results if r.success]
    if not parse_successes:
        return False, ""
    r = parse_successes[0]
    ast = apply_bindings(r.bindings.get("AST"), r.bindings)

    # Evaluate (capture stdout)
    captured = io.StringIO()
    if capture_output:
        sys.stdout = captured
    try:
        goal_eval = PredicateCall(name="eval-program", args=[ast])
        eval_results = list(ex.engine.prove_all([goal_eval]))
        success = any(r.success for r in eval_results)
    finally:
        if capture_output:
            sys.stdout = sys.__stdout__
    return success, captured.getvalue() if capture_output else ""


# ── Fact assertion tests ──────────────────────────────────────────────────────

def test_fact_assertion():
    """Facts get asserted into the graph."""
    ex = Executor()
    ex.load_file(PARSER_LOGOS)
    ex.load_file(EVALUATOR_LOGOS)

    src = 'age of alice := 30\n'
    toks = tokenize(src)
    tok_list = [[t.type, t.value] for t in toks]
    goal_parse = PredicateCall(name="parse-tokens", args=[tok_list, Variable("AST")])
    r = [x for x in ex.engine.prove_all([goal_parse]) if x.success][0]
    ast = apply_bindings(r.bindings.get("AST"), r.bindings)

    goal_eval = PredicateCall(name="eval-program", args=[ast])
    results = list(ex.engine.prove_all([goal_eval]))
    assert any(r.success for r in results)

    result = ex.engine.graph.query("alice", "age")
    assert result.found
    assert result.value == 30.0


def test_duration_fact():
    """Duration facts get asserted as DurationLit."""
    from logos.ast_nodes import DurationLit
    ex = Executor()
    ex.load_file(PARSER_LOGOS)
    ex.load_file(EVALUATOR_LOGOS)

    src = 'age of alice := 30 years\n'
    toks = tokenize(src)
    tok_list = [[t.type, t.value] for t in toks]
    goal_parse = PredicateCall(name="parse-tokens", args=[tok_list, Variable("AST")])
    r = [x for x in ex.engine.prove_all([goal_parse]) if x.success][0]
    ast = apply_bindings(r.bindings.get("AST"), r.bindings)

    goal_eval = PredicateCall(name="eval-program", args=[ast])
    list(ex.engine.prove_all([goal_eval]))

    result = ex.engine.graph.query("alice", "age")
    assert result.found
    assert isinstance(result.value, DurationLit)
    assert result.value.amount == 30.0
    assert result.value.unit == "years"


# ── Unit rule tests ───────────────────────────────────────────────────────────

def test_unit_rule_registration():
    """Unit rules (facts) get registered in the engine."""
    ex = Executor()
    ex.load_file(PARSER_LOGOS)
    ex.load_file(EVALUATOR_LOGOS)

    src = 'logos-keyword("if")\n'
    toks = tokenize(src)
    tok_list = [[t.type, t.value] for t in toks]
    goal_parse = PredicateCall(name="parse-tokens", args=[tok_list, Variable("AST")])
    r = [x for x in ex.engine.prove_all([goal_parse]) if x.success][0]
    ast = apply_bindings(r.bindings.get("AST"), r.bindings)

    goal_eval = PredicateCall(name="eval-program", args=[ast])
    list(ex.engine.prove_all([goal_eval]))

    # The rule should now be in the engine
    rule_names = [r.head.name for r in ex.engine.rules]
    assert "logos-keyword" in rule_names


# ── Bool query tests ──────────────────────────────────────────────────────────

def test_bool_query_output(capsys):
    """Bool queries print correct true/false output."""
    success, output = run_logos_program(
        'age of alice := 30 years\n'
        'can-vote(P) if:\n'
        '  P.age >= 18 years\n'
        'query: can-vote(alice)?\n',
        capture_output=False,
    )
    captured = capsys.readouterr()
    assert "can-vote" in captured.out
    assert "true" in captured.out


def test_bool_query_false(capsys):
    """Bool queries print false for non-matching queries."""
    success, output = run_logos_program(
        'age of bob := 17 years\n'
        'can-vote(P) if:\n'
        '  P.age >= 18 years\n'
        'query: can-vote(bob)?\n',
        capture_output=False,
    )
    captured = capsys.readouterr()
    assert "false" in captured.out


# ── Full program test ─────────────────────────────────────────────────────────

def test_voting_program(capsys):
    """Full voting program produces correct output."""
    src = """\
age of alice := 30 years
citizenship of alice := "US"
age of bob := 17 years
citizenship of bob := "US"
can-vote(P) if:
  P.age >= 18 years
  P.citizenship = "US"
query: can-vote(alice)?
query: can-vote(bob)?
"""
    success, _ = run_logos_program(src, capture_output=False)
    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    # Find alice and bob results
    alice_line = next((l for l in lines if "alice" in l), None)
    bob_line = next((l for l in lines if "bob" in l), None)
    assert alice_line and "true" in alice_line
    assert bob_line and "false" in bob_line
