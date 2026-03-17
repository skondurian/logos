"""
Phase E test: verify parser.logos produces correct AST from token lists.

Exit criterion from roadmap:
    parse-tokens(Tokens, AstRoot) produces correct AST facts for example programs.
"""
from __future__ import annotations
import os
import pytest

from logos.executor import Executor
from logos.lexer import tokenize
from logos.ast_nodes import Variable, PredicateCall
from logos.inference import apply_bindings


PARSER_LOGOS = os.path.join(
    os.path.dirname(__file__), "..", "logos", "parser.logos"
)


def make_executor():
    ex = Executor()
    ex.load_file(PARSER_LOGOS)
    return ex


def run_parse(ex: Executor, source: str):
    """Parse a Logos source string via parser.logos. Returns resolved AST."""
    toks = tokenize(source)
    tok_list = [[t.type, t.value] for t in toks]
    goal = PredicateCall(name="parse-tokens", args=[tok_list, Variable("AST")])
    results = list(ex.engine.prove_all([goal]))
    successes = [r for r in results if r.success]
    assert successes, f"parse-tokens failed for:\n{source}"
    r = successes[0]
    return apply_bindings(r.bindings.get("AST"), r.bindings)


def run_parse_stmt(ex: Executor, source: str):
    """Parse a single statement. Returns the first successful result."""
    toks = tokenize(source)
    tok_list = [[t.type, t.value] for t in toks]
    goal = PredicateCall(name="parse-stmt", args=[Variable("Stmt"), tok_list, Variable("Rest")])
    results = list(ex.engine.prove_all([goal]))
    successes = [r for r in results if r.success]
    assert successes, f"parse-stmt failed for: {source!r}"
    r = successes[0]
    return apply_bindings(r.bindings.get("Stmt"), r.bindings)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ex():
    return make_executor()


# ── Import statements ──────────────────────────────────────────────────────────

def test_import_wildcard(ex):
    stmt = run_parse_stmt(ex, 'import * from "stdlib/lists"')
    assert stmt == ["import", "*", '"stdlib/lists"']


def test_import_named(ex):
    stmt = run_parse_stmt(ex, 'import lists from "stdlib/lists"')
    assert stmt[0] == "import"
    assert stmt[1] == "lists"
    assert stmt[2] == '"stdlib/lists"'


# ── Semantic bindings ──────────────────────────────────────────────────────────

def test_bind_of_form(ex):
    stmt = run_parse_stmt(ex, "age of alice := 30")
    assert stmt == ["bind", "alice", "age", 30.0]


def test_bind_duration(ex):
    stmt = run_parse_stmt(ex, "age of alice := 30 years")
    assert stmt == ["bind", "alice", "age", ["duration", 30.0, "years"]]


def test_bind_string(ex):
    stmt = run_parse_stmt(ex, 'citizenship of alice := "US"')
    assert stmt == ["bind", "alice", "citizenship", '"US"']


def test_bind_dot_form(ex):
    stmt = run_parse_stmt(ex, 'alice.score := 95.0')
    assert stmt == ["bind", "alice", "score", 95.0]


# ── Unit rules (facts) ────────────────────────────────────────────────────────

def test_unit_rule_one_arg(ex):
    stmt = run_parse_stmt(ex, 'logos-keyword("if")')
    assert stmt == ["unit", "logos-keyword", ['"if"']]


def test_unit_rule_no_args(ex):
    stmt = run_parse_stmt(ex, "is-valid()")
    assert stmt == ["unit", "is-valid", []]


def test_unit_rule_multi_args(ex):
    stmt = run_parse_stmt(ex, 'pair("a", "b")')
    assert stmt == ["unit", "pair", ['"a"', '"b"']]


# ── Inference rules ───────────────────────────────────────────────────────────

def test_inference_rule_simple(ex):
    src = "can-vote(P) if:\n  age(P, A)\n"
    stmt = run_parse_stmt(ex, src)
    assert stmt[0] == "rule"
    assert stmt[1] == "can-vote"
    assert stmt[2] == [["var", "P"]]
    conds = stmt[3]
    assert len(conds) == 1
    assert conds[0] == ["call", "age", [["var", "P"], ["var", "A"]]]


def test_inference_rule_comparison(ex):
    src = "can-vote(P) if:\n  P.age >= 18 years\n  P.citizenship = \"US\"\n"
    stmt = run_parse_stmt(ex, src)
    assert stmt[0] == "rule"
    conds = stmt[3]
    assert len(conds) == 2
    assert conds[0] == ["cmp", ["path-var", "P", "age"], ">=", ["duration", 18.0, "years"]]
    assert conds[1] == ["cmp", ["path-var", "P", "citizenship"], "=", '"US"']


def test_inference_rule_negated(ex):
    src = "eligible(P) if:\n  not banned(P)\n  age(P, A)\n"
    stmt = run_parse_stmt(ex, src)
    assert stmt[0] == "rule"
    conds = stmt[3]
    assert conds[0] == ["not-call", "banned", [["var", "P"]]]


# ── Queries ───────────────────────────────────────────────────────────────────

def test_bool_query_with_colon(ex):
    stmt = run_parse_stmt(ex, "query: can-vote(alice)?")
    assert stmt == ["query-bool", "can-vote", [["id", "alice"]]]


def test_bool_query_without_colon(ex):
    stmt = run_parse_stmt(ex, "query can-vote(alice)")
    assert stmt[0] == "query-bool"
    assert stmt[1] == "can-vote"


def test_find_query(ex):
    stmt = run_parse_stmt(ex, "find P where can-vote(P)")
    assert stmt[0] == "query-find"
    assert stmt[1] == ["P"]
    assert stmt[2] == [["call", "can-vote", [["var", "P"]]]]


# ── Full program parsing ──────────────────────────────────────────────────────

def test_parse_full_program(ex):
    src = """\
import * from "stdlib/lists"
age of alice := 30 years
citizenship of alice := "US"
can-vote(P) if:
  P.age >= 18 years
  P.citizenship = "US"
query: can-vote(alice)?
find P where can-vote(P)
"""
    ast = run_parse(ex, src)
    assert ast[0] == "program"
    stmts = ast[1]
    assert len(stmts) == 6
    assert stmts[0] == ["import", "*", '"stdlib/lists"']
    assert stmts[1] == ["bind", "alice", "age", ["duration", 30.0, "years"]]
    assert stmts[2] == ["bind", "alice", "citizenship", '"US"']
    assert stmts[3][0] == "rule"
    assert stmts[4] == ["query-bool", "can-vote", [["id", "alice"]]]
    assert stmts[5][0] == "query-find"


def test_empty_program(ex):
    ast = run_parse(ex, "")
    assert ast == ["program", []]


def test_program_with_comments(ex):
    src = """\
// This is a comment
age of alice := 30
// Another comment
"""
    ast = run_parse(ex, src)
    assert ast[0] == "program"
    stmts = ast[1]
    assert len(stmts) == 1
    assert stmts[0] == ["bind", "alice", "age", 30.0]
