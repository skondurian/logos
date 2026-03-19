"""
Phase 8 tests: lex-file and lex-source primitives.

Both produce a cons-list of [type, value] pairs that matches the
output of logos/lexer.py tokenize().
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from logos.compiler import compile_file

LOGOS_DIR = Path(__file__).parent.parent


def _run(src: str, tmp_path) -> str:
    f = tmp_path / "prog.logos"
    f.write_text(src)
    out = str(tmp_path / "bin")
    compile_file(str(f), out)
    result = subprocess.run([out], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout


# ── lex-source ────────────────────────────────────────────────────────────────

def test_lex_source_identifier(tmp_path):
    """A bare identifier is tokenized as IDENTIFIER."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("hello", Tokens)
          list-head(Tokens, Tok)
          list-head(Tok, "IDENTIFIER")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_variable(tmp_path):
    """Uppercase-first identifier becomes VARIABLE."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("Foo", Tokens)
          list-head(Tokens, Tok)
          list-head(Tok, "VARIABLE")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_number(tmp_path):
    """An integer is tokenized as NUMBER."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("42", Tokens)
          list-head(Tokens, Tok)
          list-head(Tok, "NUMBER")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_string_token(tmp_path):
    """A quoted string is tokenized as STRING."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("\\\"hello\\\"", Tokens)
          list-head(Tokens, Tok)
          list-head(Tok, "STRING")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_keyword(tmp_path):
    """'if' is classified as KEYWORD."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("if", Tokens)
          list-head(Tokens, Tok)
          list-head(Tok, "KEYWORD")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_hyphenated_identifier(tmp_path):
    """Hyphenated names like lex-file are a single IDENTIFIER token."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("lex-file", Tokens)
          list-head(Tokens, Tok)
          list-head(Tok, "IDENTIFIER")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_identifier_value(tmp_path):
    """The value of the first token for 'hello' is 'hello'."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("hello", Tokens)
          list-head(Tokens, Tok)
          list-nth(Tok, 1.0, "hello")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_eof_at_end(tmp_path):
    """The last token is always EOF."""
    stdout = _run(textwrap.dedent("""\
        check() if:
          lex-source("hello", Tokens)
          list-reverse(Tokens, Rev)
          list-head(Rev, Last)
          list-head(Last, "EOF")
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_source_indent_dedent(tmp_path):
    """An indented block produces INDENT then DEDENT."""
    stdout = _run(textwrap.dedent("""\
        has-indent() if:
          lex-source("foo() if:\\n  bar()\\n", Tokens)
          list-nth(Tokens, 6.0, IndentTok)
          list-head(IndentTok, "INDENT")
        query: has-indent()?
    """), tmp_path)
    assert "true" in stdout


# ── lex-file ──────────────────────────────────────────────────────────────────

def test_lex_file_hello_example(tmp_path):
    """lex-file on 01_hello_facts.logos returns a non-empty token list."""
    logos_file = str(LOGOS_DIR / "examples" / "01_hello_facts.logos")
    stdout = _run(textwrap.dedent(f"""\
        check() if:
          lex-file("{logos_file}", Tokens)
          list-head(Tokens, _Tok)
        query: check()?
    """), tmp_path)
    assert "true" in stdout


def test_lex_file_missing_path_fails(tmp_path):
    """lex-file on a missing path makes the query false."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          lex-file("/nonexistent/path.logos", _Tokens)
        query: setup()?
    """), tmp_path)
    assert "false" in stdout
