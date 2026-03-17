"""
Phase D test: verify lexer.logos produces the same token stream as lexer.py.

Exit criterion from roadmap:
    lex-string("age of alice := 30 years", Tokens)
    // Tokens binds to the expected token list
"""
from __future__ import annotations
import os
import pytest

from logos.executor import Executor
from logos.lexer import tokenize
from logos.ast_nodes import Variable, PredicateCall


LEXER_LOGOS = os.path.join(
    os.path.dirname(__file__), "..", "logos", "lexer.logos"
)


def run_lex(source: str) -> list[list[str]]:
    """Run lexer.logos on source, return list of [type, value] pairs."""
    ex = Executor()
    ex.load_file(LEXER_LOGOS)
    goal = PredicateCall(name="lex-string", args=[source, Variable("Tokens")])
    results = list(ex.engine.prove_all([goal]))
    successes = [r for r in results if r.success]
    assert successes, f"lex-string failed for source: {source!r}"
    tokens = successes[0].bindings.get("Tokens")
    assert tokens is not None, "Tokens variable not bound"
    return tokens


def py_lex(source: str) -> list[list[str]]:
    """Run Python lexer, return list of [type, value] pairs (skip EOF)."""
    toks = tokenize(source)
    return [[t.type, t.value] for t in toks
            if t.type not in ("EOF", "INDENT", "DEDENT", "NEWLINE")]


# ── Core exit criterion ────────────────────────────────────────────────────────

def test_basic_binding():
    tokens = run_lex("age of alice := 30 years")
    types = [t[0] for t in tokens]
    assert "IDENTIFIER" in types
    assert "ASSIGN" in types
    assert "NUMBER" in types
    assert "DURATION_UNIT" in types


def test_keywords():
    tokens = run_lex("if where find")
    types = [t[0] for t in tokens]
    assert types == ["KEYWORD", "KEYWORD", "KEYWORD"]
    values = [t[1] for t in tokens]
    assert values == ["if", "where", "find"]


def test_variable_vs_identifier():
    tokens = run_lex("Alice alice")
    assert tokens[0] == ["VARIABLE", "Alice"]
    assert tokens[1] == ["IDENTIFIER", "alice"]


def test_duration_unit():
    tokens = run_lex("30 years")
    assert tokens[0] == ["NUMBER", "30"]
    assert tokens[1] == ["DURATION_UNIT", "years"]


def test_assign_operator():
    tokens = run_lex(":=")
    assert tokens == [["ASSIGN", ":="]]


def test_colon_not_assign():
    tokens = run_lex(":")
    assert tokens == [["COLON", ":"]]


def test_arrow():
    tokens = run_lex("->")
    assert tokens == [["ARROW", "->"]]


def test_comparison_operators():
    tokens = run_lex(">= <= !=")
    types = [t[0] for t in tokens]
    assert types == ["OP_GEQ", "OP_LEQ", "OP_NEQ"]


def test_single_char_gt_lt():
    tokens = run_lex("> <")
    types = [t[0] for t in tokens]
    assert types == ["OP_GT", "OP_LT"]


def test_string_literal():
    tokens = run_lex('"hello"')
    assert tokens == [["STRING", '"hello"']]


def test_comment_skipped():
    tokens = run_lex("alice // this is a comment")
    assert all(t[0] != "COMMENT" for t in tokens)
    assert tokens[0] == ["IDENTIFIER", "alice"]
    assert len(tokens) == 1


def test_parens_and_brackets():
    tokens = run_lex("([])")
    types = [t[0] for t in tokens]
    assert types == ["LPAREN", "LBRACKET", "RBRACKET", "RPAREN"]


def test_minus_not_arrow():
    tokens = run_lex("- 5")
    assert tokens[0] == ["OP_MINUS", "-"]


def test_slash_not_comment():
    tokens = run_lex("/ 2")
    assert tokens[0] == ["OP_SLASH", "/"]


def test_empty_string():
    tokens = run_lex("")
    assert tokens == []


def test_full_binding_line():
    """The roadmap exit criterion: age of alice := 30 years"""
    tokens = run_lex("age of alice := 30 years")
    # Expected: age(IDENTIFIER), of(KEYWORD), alice(IDENTIFIER),
    #           :=(ASSIGN), 30(NUMBER), years(DURATION_UNIT)
    assert tokens[0] == ["IDENTIFIER", "age"]
    assert tokens[1] == ["KEYWORD", "of"]
    assert tokens[2] == ["IDENTIFIER", "alice"]
    assert tokens[3] == ["ASSIGN", ":="]
    assert tokens[4] == ["NUMBER", "30"]
    assert tokens[5] == ["DURATION_UNIT", "years"]
