"""
Phase 3 tests: string primitives.
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


# ── str-concat ────────────────────────────────────────────────────────────────

def test_str_concat_generates_prim():
    prog = parse('check(R) if:\n  str-concat("hello", " world", R)\n')
    assert "logos_prim_str_concat" in Compiler(prog).generate()


def test_str_concat_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        greet(R) if:
          str-concat("Hello", " World", R)
        query: greet("Hello World")?
        query: greet("Goodbye")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "Hello World" in l)
    assert any("false" in l for l in lines if "Goodbye"     in l)


# ── str-length ────────────────────────────────────────────────────────────────

def test_str_length_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        len-check(S, N) if:
          str-length(S, N)
        query: len-check("hello", 5.0)?
        query: len-check("hello", 3.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "5" in l)
    assert any("false" in l for l in lines if "3" in l)


# ── str-starts-with / str-ends-with ──────────────────────────────────────────

def test_str_starts_with_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        prefix-ok(S) if:
          str-starts-with(S, "He")
        query: prefix-ok("Hello")?
        query: prefix-ok("World")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "Hello" in l)
    assert any("false" in l for l in lines if "World" in l)


def test_str_ends_with_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        suffix-ok(S) if:
          str-ends-with(S, "lo")
        query: suffix-ok("hello")?
        query: suffix-ok("world")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "hello" in l)
    assert any("false" in l for l in lines if "world" in l)


# ── str-to-number / number-to-str ─────────────────────────────────────────────

def test_str_to_number_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        parse-check(S, N) if:
          str-to-number(S, N)
        query: parse-check("3.14", 3.14)?
        query: parse-check("abc", 1.0)?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "3.14" in l)
    assert any("false" in l for l in lines if "abc"  in l)


def test_number_to_str_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        num-str(N, S) if:
          number-to-str(N, S)
        query: num-str(42.0, "42")?
        query: num-str(42.0, "99")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "42" in l)
    assert any("false" in l for l in lines if "99" in l)


# ── str-upper / str-lower ─────────────────────────────────────────────────────

def test_str_upper_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        upper-check(S, U) if:
          str-upper(S, U)
        query: upper-check("hello", "HELLO")?
        query: upper-check("hello", "hello")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "HELLO" in l)
    assert any("false" in l for l in lines if "hello" in l and "HELLO" not in l)


def test_str_lower_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        lower-check(S, L) if:
          str-lower(S, L)
        query: lower-check("HELLO", "hello")?
    """), tmp_path)
    assert "true" in stdout


# ── str-contains ─────────────────────────────────────────────────────────────

def test_str_contains_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        has-sub(S) if:
          str-contains(S, "ell")
        query: has-sub("hello")?
        query: has-sub("world")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "hello" in l)
    assert any("false" in l for l in lines if "world" in l)


# ── str-split ────────────────────────────────────────────────────────────────

def test_str_split_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        split-check(S, Sep, L) if:
          str-split(S, Sep, L)
        query: split-check("a,b,c", ",", ["a", "b", "c"])?
        query: split-check("a,b,c", ",", ["a", "b"])?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "a, b, c" in l or "[a, b, c]" in l)
    assert any("false" in l for l in lines if "a, b]"   in l or "[a, b]"    in l)


# ── char predicates ───────────────────────────────────────────────────────────

def test_char_alpha_compiles(tmp_path):
    stdout = _run(textwrap.dedent("""\
        alpha-check(C) if:
          char-alpha(C)
        query: alpha-check("a")?
        query: alpha-check("1")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "a" in l)
    assert any("false" in l for l in lines if "1" in l)


# ── stdlib/strings.logos compiles ────────────────────────────────────────────

def test_strings_stdlib_compiles(tmp_path):
    strings_path = LOGOS_DIR / "logos" / "stdlib" / "strings.logos"
    lists_path   = LOGOS_DIR / "logos" / "stdlib" / "lists.logos"
    if not strings_path.exists():
        pytest.skip("stdlib/strings.logos not found")

    driver = tmp_path / "driver.logos"
    driver.write_text(textwrap.dedent(f"""\
        import * from "{lists_path}"
        import * from "{strings_path}"
        query: str-concat("foo", "bar", "foobar")?
        query: str-starts-with("hello", "he")?
        query: str-non-empty("x")?
        query: str-non-empty("")?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(driver), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    stdout = result.stdout
    assert any("true"  in l for l in stdout.splitlines() if "foobar" in l)
    assert any("true"  in l for l in stdout.splitlines() if "he"     in l)
    assert any("true"  in l for l in stdout.splitlines() if "x"      in l)
    assert any("false" in l for l in stdout.splitlines() if '""'      in l
               or "str-non-empty()" in l)
