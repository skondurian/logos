"""Tests for the Logos lexer."""

import pytest
from logos.lexer import tokenize, tokenize_raw, Token


def tok_types(source: str) -> list[str]:
    return [t.type for t in tokenize(source) if t.type != "EOF"]


def tok_values(source: str) -> list[str]:
    return [t.value for t in tokenize(source) if t.type != "EOF"]


# ─── Basic tokens ─────────────────────────────────────────────────────────────

def test_identifier():
    tokens = [t for t in tokenize("alice") if t.type not in ("NEWLINE", "EOF")]
    assert len(tokens) == 1
    assert tokens[0].type == "IDENTIFIER"
    assert tokens[0].value == "alice"

def test_variable():
    tokens = [t for t in tokenize("Person") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "VARIABLE" for t in tokens)

def test_number():
    tokens = [t for t in tokenize("42") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "NUMBER" for t in tokens)

def test_float():
    tokens = [t for t in tokenize("3.14") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "NUMBER" for t in tokens)

def test_string():
    tokens = [t for t in tokenize('"hello"') if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "STRING" for t in tokens)
    assert any(t.value == '"hello"' for t in tokens)

def test_duration_unit():
    tokens = [t for t in tokenize("30 years") if t.type not in ("NEWLINE", "EOF")]
    types = [t.type for t in tokens]
    assert "NUMBER" in types
    assert "DURATION_UNIT" in types

def test_keyword_if():
    tokens = [t for t in tokenize("if") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "KEYWORD" and t.value == "if" for t in tokens)

def test_assign_operator():
    tokens = [t for t in tokenize(":=") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "ASSIGN" for t in tokens)

def test_comment_stripped():
    tokens = tokenize("alice // this is a comment")
    types = [t.type for t in tokens]
    assert "COMMENT" not in types

def test_arrow():
    tokens = [t for t in tokenize("→") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "ARROW" for t in tokens)


# ─── Indentation ──────────────────────────────────────────────────────────────

def test_indent_dedent():
    source = "Person:\n  name: HumanName\n"
    tokens = tokenize(source)
    types = [t.type for t in tokens]
    assert "INDENT" in types
    assert "DEDENT" in types

def test_nested_indent():
    source = "outer:\n  inner:\n    deep: value\n"
    tokens = tokenize(source)
    indent_count = sum(1 for t in tokens if t.type == "INDENT")
    dedent_count = sum(1 for t in tokens if t.type == "DEDENT")
    assert indent_count == dedent_count

def test_multiple_dedents():
    source = "a:\n  b:\n    c: x\nd: y\n"
    tokens = tokenize(source)
    dedents = [t for t in tokens if t.type == "DEDENT"]
    assert len(dedents) >= 2


# ─── Keywords vs identifiers ──────────────────────────────────────────────────

def test_kebab_case_identifier():
    tokens = [t for t in tokenize("can-vote") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "IDENTIFIER" and t.value == "can-vote" for t in tokens)

def test_confidence_keyword():
    tokens = [t for t in tokenize("confidence") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.type == "KEYWORD" and t.value == "confidence" for t in tokens)

def test_absolute_keyword():
    tokens = [t for t in tokenize("absolute") if t.type not in ("NEWLINE", "EOF")]
    assert any(t.value == "absolute" for t in tokens)
