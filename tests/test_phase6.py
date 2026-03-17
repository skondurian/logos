"""
Phase 6 tests: assert-fact primitive (dynamic fact assertion at runtime).
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from logos.codegen import Compiler
from logos.compiler import compile_file
from logos.parser import parse


def _run(src: str, tmp_path) -> str:
    f = tmp_path / "prog.logos"
    f.write_text(src)
    out = str(tmp_path / "bin")
    compile_file(str(f), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


# ── Basic code generation ─────────────────────────────────────────────────────

def test_assert_fact_in_primitives():
    prog = parse('setup(S, P, V) if:\n  assert-fact(S, P, V)\n')
    src = Compiler(prog).generate()
    assert "logos_prim_assert_fact" in src


# ── Runtime behaviour ─────────────────────────────────────────────────────────

def test_assert_fact_string_value(tmp_path):
    """assert-fact stores a string value; subsequent graph lookup succeeds."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          assert-fact("alice", "role", "admin")
        query: setup()?
        role-is(S, R) if:
          S.role = R
        query: role-is("alice", "admin")?
        query: role-is("alice", "guest")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true" in l for l in lines if "setup" in l)
    assert any("true"  in l for l in lines if "admin" in l)
    assert any("false" in l for l in lines if "guest" in l)


def test_assert_fact_number_value(tmp_path):
    """assert-fact stores a numeric value; comparison works afterward."""
    stdout = _run(textwrap.dedent("""\
        init() if:
          assert-fact("bob", "score", 42.0)
        query: init()?
        high-score(P) if:
          P.score >= 40.0
        query: high-score("bob")?
        query: high-score("nobody")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true" in l for l in lines if "init" in l)
    assert any("true"  in l for l in lines if "bob"    in l)
    assert any("false" in l for l in lines if "nobody" in l)


def test_assert_fact_rule_body(tmp_path):
    """assert-fact called from a rule body with variable arguments."""
    stdout = _run(textwrap.dedent("""\
        store(S, P, V) if:
          assert-fact(S, P, V)
        query: store("city", "name", "Paris")?
        name-is(S, N) if:
          S.name = N
        query: name-is("city", "Paris")?
        query: name-is("city", "London")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true" in l for l in lines if "Paris"  in l and "store" not in l)
    assert any("false" in l for l in lines if "London" in l)


def test_assert_fact_bad_subject_fails(tmp_path):
    """assert-fact fails (returns false) when subject is not a string."""
    stdout = _run(textwrap.dedent("""\
        bad-assert() if:
          assert-fact(42.0, "key", "val")
        query: bad-assert()?
    """), tmp_path)
    assert "false" in stdout


def test_assert_fact_multiple(tmp_path):
    """Multiple assert-fact calls in sequence all take effect."""
    stdout = _run(textwrap.dedent("""\
        populate() if:
          assert-fact("x", "color", "red")
          assert-fact("y", "color", "blue")
        query: populate()?
        color-of(S, C) if:
          S.color = C
        query: color-of("x", "red")?
        query: color-of("y", "blue")?
        query: color-of("x", "blue")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "red"  in l and "color-of" in l)
    assert any("true"  in l for l in lines if "blue" in l and "y"        in l)
    assert any("false" in l for l in lines if "blue" in l and "x"        in l)
