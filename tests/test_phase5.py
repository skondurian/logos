"""
Phase 5 tests: ListLit in rule head arguments (head pattern matching).
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from logos.codegen import Compiler
from logos.compiler import compile_file
from logos.parser import parse

LOGOS_DIR = Path(__file__).parent.parent


def _run(src: str, tmp_path) -> str:
    """Write src to a .logos file, compile, run, return stdout."""
    f = tmp_path / "prog.logos"
    f.write_text(src)
    out = str(tmp_path / "bin")
    compile_file(str(f), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


# ── Literal list in head (constant matching) ──────────────────────────────────

def test_literal_list_head_generates(tmp_path):
    """Rule with a literal list in the head can be generated without error."""
    src = textwrap.dedent("""\
        match-pair([\"a\", \"b\"]) if:
          true
        query: match-pair([\"a\", \"b\"])?
        query: match-pair([\"a\", \"c\"])?
    """)
    stdout = _run(src, tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "a" in l and "b" in l)
    assert any("false" in l for l in lines if "a" in l and "c" in l)


# ── Variable extraction from head ListLit ────────────────────────────────────

def test_head_list_binds_vars(tmp_path):
    """Variables inside a head ListLit are bound from the caller's list arg."""
    src = textwrap.dedent("""\
        first-two([A, B, C], A, B) if:
          true
        query: first-two([\"x\", \"y\", \"z\"], \"x\", \"y\")?
        query: first-two([\"x\", \"y\", \"z\"], \"x\", \"z\")?
    """)
    stdout = _run(src, tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines)
    assert any("false" in l for l in lines)


def test_head_list_first_element(tmp_path):
    """Extract the first element of a known-length list via head pattern."""
    src = textwrap.dedent("""\
        get-first([H, T], H) if:
          true
        query: get-first([\"hello\", \"world\"], \"hello\")?
        query: get-first([\"hello\", \"world\"], \"world\")?
    """)
    stdout = _run(src, tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "hello" in l)
    # second query: pattern [var_H, T] bound to ["hello","world"], H="hello" != "world"
    assert any("false" in l for l in lines if "world" in l)


# ── Head ListLit with shared variable in another head arg ─────────────────────

def test_head_list_shared_var(tmp_path):
    """A variable appearing in both the ListLit pattern and another head arg
    causes unification between the list element and the other arg."""
    src = textwrap.dedent("""\
        same-first([H, W], H) if:
          true
        query: same-first([\"a\", \"b\"], \"a\")?
        query: same-first([\"a\", \"b\"], \"b\")?
    """)
    stdout = _run(src, tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "a" in l)
    assert any("false" in l for l in lines if "b" in l)


# ── Head ListLit with body condition ─────────────────────────────────────────

def test_head_list_with_body_condition(tmp_path):
    """Head list pattern + a body primitive condition using the extracted variable."""
    src = textwrap.dedent("""\
        starts-hi([H, T], H) if:
          str-starts-with(H, \"hi\")
        query: starts-hi([\"hi\", \"there\"], \"hi\")?
        query: starts-hi([\"bye\", \"there\"], \"bye\")?
    """)
    stdout = _run(src, tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "hi" in l)
    assert any("false" in l for l in lines if "bye" in l)


# ── Multiclause predicate with ListLit in one clause ─────────────────────────

def test_multiclause_with_list_head(tmp_path):
    """Multiple clauses: one with a ListLit head arg, one without."""
    src = textwrap.dedent("""\
        describe([\"a\", \"b\"], \"two\") if:
          true
        describe([\"a\", \"b\", \"c\"], \"three\") if:
          true
        query: describe([\"a\", \"b\"], \"two\")?
        query: describe([\"a\", \"b\"], \"three\")?
        query: describe([\"a\", \"b\", \"c\"], \"three\")?
    """)
    stdout = _run(src, tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "two" in l)
    assert any("false" in l for l in lines if "three" in l and "two" not in l)
    assert any("true"  in l for l in lines if "three" in l)
