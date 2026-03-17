"""
Variable comparison tests: X >= Y, N > 0, etc. where both sides are
variables or literals rather than graph paths (subject.predicate OP value).
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from logos.compiler import compile_file

LOGOS_DIR = Path(__file__).parent.parent


def _run(src: str, tmp_path) -> str:
    f = tmp_path / "prog.logos"
    f.write_text(src)
    out = str(tmp_path / "bin")
    compile_file(str(f), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


# ── Basic operators ───────────────────────────────────────────────────────────

def test_var_ge_literal(tmp_path):
    stdout = _run(textwrap.dedent("""\
        big(X) if:
          X >= 10.0
        query: big(10.0)?
        query: big(9.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "10" in l)
    assert any("false" in l for l in lines if "9"  in l)


def test_var_gt_literal(tmp_path):
    stdout = _run(textwrap.dedent("""\
        positive(X) if:
          X > 0.0
        query: positive(1.0)?
        query: positive(0.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "1" in l)
    assert any("false" in l for l in lines if "0" in l)


def test_var_le_literal(tmp_path):
    stdout = _run(textwrap.dedent("""\
        small(X) if:
          X <= 5.0
        query: small(5.0)?
        query: small(6.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "5" in l)
    assert any("false" in l for l in lines if "6" in l)


def test_var_lt_literal(tmp_path):
    stdout = _run(textwrap.dedent("""\
        negative(X) if:
          X < 0.0
        query: negative(-1.0)?
        query: negative(0.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "-1" in l)
    assert any("false" in l for l in lines if "0"  in l)


def test_var_eq_literal(tmp_path):
    stdout = _run(textwrap.dedent("""\
        is-zero(X) if:
          X = 0.0
        query: is-zero(0.0)?
        query: is-zero(1.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "0" in l)
    assert any("false" in l for l in lines if "1" in l)


def test_var_ne_literal(tmp_path):
    stdout = _run(textwrap.dedent("""\
        nonzero(X) if:
          X != 0.0
        query: nonzero(1.0)?
        query: nonzero(0.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "1" in l)
    assert any("false" in l for l in lines if "0" in l)


# ── Variable vs variable ──────────────────────────────────────────────────────

def test_var_vs_var(tmp_path):
    stdout = _run(textwrap.dedent("""\
        in-range(Lo, Hi, X) if:
          X >= Lo
          X <= Hi
        query: in-range(1.0, 10.0, 5.0)?
        query: in-range(1.0, 10.0, 0.0)?
        query: in-range(1.0, 10.0, 11.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "5"  in l)
    assert any("false" in l for l in lines if "0"  in l)
    assert any("false" in l for l in lines if "11" in l)


# ── Combined with arithmetic primitives ──────────────────────────────────────

def test_var_compare_after_arith(tmp_path):
    """Comparison on the result of a num-* primitive."""
    stdout = _run(textwrap.dedent("""\
        even(X) if:
          num-mod(X, 2.0, R)
          R = 0.0
        query: even(4.0)?
        query: even(3.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "4" in l)
    assert any("false" in l for l in lines if "3" in l)


def test_str_length_compare(tmp_path):
    """str-length result compared to a literal."""
    stdout = _run(textwrap.dedent("""\
        long-str(S) if:
          str-length(S, N)
          N >= 5.0
        query: long-str(\"hello\")?
        query: long-str(\"hi\")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "hello" in l)
    assert any("false" in l for l in lines if "hi"    in l)


# ── stdlib/math.logos compiles and runs ───────────────────────────────────────

def test_math_stdlib_compiles(tmp_path):
    math_path = LOGOS_DIR / "logos" / "stdlib" / "math.logos"
    if not math_path.exists():
        pytest.skip("stdlib/math.logos not found")

    driver = tmp_path / "driver.logos"
    driver.write_text(textwrap.dedent(f"""\
        import * from "{math_path}"
        query: positive(5.0)?
        query: positive(-1.0)?
        query: negative(-3.0)?
        query: non-negative(0.0)?
        query: between(1.0, 10.0, 5.0)?
        query: between(1.0, 10.0, 11.0)?
        query: even(4.0)?
        query: odd(3.0)?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(driver), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    lines  = stdout.splitlines()
    assert any("true"  in l for l in lines if "5"  in l and "positive" in l)
    assert any("false" in l for l in lines if "-1" in l)
    assert any("true"  in l for l in lines if "-3" in l)
    assert any("true"  in l for l in lines if "non-negative" in l)
    assert any("true"  in l for l in lines if "between" in l and "5" in l)
    assert any("false" in l for l in lines if "11" in l)
    assert any("true"  in l for l in lines if "even" in l)
    assert any("true"  in l for l in lines if "odd"  in l)
