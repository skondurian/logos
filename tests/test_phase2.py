"""
Phase 2 tests: core primitives (list-cons, list-empty, equal, num-add, …).
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


# ── equal primitive ───────────────────────────────────────────────────────────

def test_equal_generates_prim_equal():
    prog     = parse('check(X) if:\n  equal(X, "hello")\nquery: check("hello")?\n')
    c_source = Compiler(prog).generate()
    assert "logos_prim_equal" in c_source


def test_equal_compiles_and_runs(tmp_path):
    src = tmp_path / "eq.logos"
    src.write_text(textwrap.dedent("""\
        check(X) if:
          equal(X, "yes")
        query: check("yes")?
        query: check("no")?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(src), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    lines = result.stdout
    assert "check(yes)" in lines and "true"  in lines
    assert "check(no)"  in lines and "false" in lines


# ── list-cons / list-empty primitives ─────────────────────────────────────────

def test_list_cons_generates_prim():
    prog     = parse("first(H, L) if:\n  list-cons(H, T, L)\n")
    c_source = Compiler(prog).generate()
    assert "logos_prim_list_cons" in c_source


def test_body_local_var_allocated():
    """Body-local variable T must be allocated with logos_alloc_var."""
    prog     = parse("first(H, L) if:\n  list-cons(H, T, L)\n")
    c_source = Compiler(prog).generate()
    assert "logos_alloc_var" in c_source
    assert "var_T" in c_source


def test_list_cons_rule_compiles(tmp_path):
    src = tmp_path / "lc.logos"
    src.write_text(textwrap.dedent("""\
        items := ["a", "b", "c"]
        first(H, L) if:
          list-cons(H, T, L)
        query: first("a", [\"a\", \"b\", \"c\"])?
        query: first("z", [\"a\", \"b\", \"c\"])?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(src), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    stdout = result.stdout
    assert "true"  in stdout.split("first(a")[1].split("\n")[0]
    assert "false" in stdout.split("first(z")[1].split("\n")[0]


def test_list_empty_rule_compiles(tmp_path):
    src = tmp_path / "le.logos"
    src.write_text(textwrap.dedent("""\
        empty-check(L) if:
          list-empty(L)
        query: empty-check([])?
        query: empty-check(["x"])?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(src), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    stdout = result.stdout
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "empty-check([])"  in l)
    assert any("false" in l for l in lines if "empty-check([x])" in l)


# ── num-add / num-max / num-min ───────────────────────────────────────────────

def test_num_add_compiles(tmp_path):
    src = tmp_path / "na.logos"
    src.write_text(textwrap.dedent("""\
        add-three(A, B, C) if:
          num-add(A, B, C)
        query: add-three(1.0, 2.0, 3.0)?
        query: add-three(1.0, 2.0, 5.0)?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(src), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    stdout = result.stdout
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "3.0" in l and "add-three" in l)
    assert any("false" in l for l in lines if "5.0" in l and "add-three" in l)


# ── stdlib/lists.logos compiles without error ─────────────────────────────────

def test_lists_stdlib_compiles(tmp_path):
    """stdlib/lists.logos should compile and link without error."""
    lists_path = LOGOS_DIR / "logos" / "stdlib" / "lists.logos"
    if not lists_path.exists():
        pytest.skip("stdlib/lists.logos not found")

    driver = tmp_path / "driver.logos"
    driver.write_text(textwrap.dedent(f"""\
        import * from "{lists_path}"
        query: list-member("b", ["a", "b", "c"])?
        query: list-member("z", ["a", "b", "c"])?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(driver), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0


def test_list_member_correct_output(tmp_path):
    """list-member should return true for members, false otherwise."""
    lists_path = LOGOS_DIR / "logos" / "stdlib" / "lists.logos"
    if not lists_path.exists():
        pytest.skip("stdlib/lists.logos not found")

    driver = tmp_path / "driver.logos"
    driver.write_text(textwrap.dedent(f"""\
        import * from "{lists_path}"
        query: list-member("b", ["a", "b", "c"])?
        query: list-member("z", ["a", "b", "c"])?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(driver), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    stdout = result.stdout
    assert any("true"  in l for l in stdout.splitlines() if "b"  in l and "list-member" in l)
    assert any("false" in l for l in stdout.splitlines() if "z"  in l and "list-member" in l)


# ── list-sum via stdlib ───────────────────────────────────────────────────────

def test_list_sum_correct(tmp_path):
    """list-sum([1,2,3], S) should yield S=6."""
    lists_path = LOGOS_DIR / "logos" / "stdlib" / "lists.logos"
    if not lists_path.exists():
        pytest.skip("stdlib/lists.logos not found")

    driver = tmp_path / "driver.logos"
    driver.write_text(textwrap.dedent(f"""\
        import * from "{lists_path}"
        query: list-sum([1, 2, 3], 6.0)?
        query: list-sum([1, 2, 3], 7.0)?
    """))
    out = str(tmp_path / "bin")
    compile_file(str(driver), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    stdout = result.stdout
    assert any("true"  in l for l in stdout.splitlines() if "6" in l)
    assert any("false" in l for l in stdout.splitlines() if "7" in l)
