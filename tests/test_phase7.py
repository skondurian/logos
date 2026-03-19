"""
Phase 7 tests: meta-interpreter primitives.
  register-rule-ast(Name, Args, Conditions)
  exec-bool-query-ast(Name, QueryArgs)
  exec-find-query-ast(VarNames, Conditions)
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
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


# ── register-rule-ast basic ───────────────────────────────────────────────────

def test_register_and_query_unit_rule(tmp_path):
    """register a unit rule (no conditions) and query it."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("warm", ["summer"], [])
          register-rule-ast("warm", ["winter"], [])
          exec-bool-query-ast("warm", ["summer"])
          exec-bool-query-ast("warm", ["spring"])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "summer" in l)
    assert any("false" in l for l in lines if "spring" in l)


def test_register_rule_with_variable_arg(tmp_path):
    """Rule with a variable head arg: any value matches."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("any-val", [["var", "X"]], [])
          exec-bool-query-ast("any-val", ["hello"])
          exec-bool-query-ast("any-val", [42.0])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true" in l for l in lines if "hello" in l)
    assert any("true" in l for l in lines if "42"    in l)


# ── register-rule-ast with conditions ────────────────────────────────────────

def test_register_rule_with_primitive_condition(tmp_path):
    """Rule body condition calls a primitive."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("starts-he", [["var", "S"]], [["call", "str-starts-with", [["var", "S"], "he"]]])
          exec-bool-query-ast("starts-he", ["hello"])
          exec-bool-query-ast("starts-he", ["world"])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "hello" in l)
    assert any("false" in l for l in lines if "world" in l)


def test_register_rule_with_comparison_condition(tmp_path):
    """Rule body condition is a comparison (["cmp", Left, Op, Right])."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("big", [["var", "N"]], [["cmp", ["var", "N"], ">=", 10.0]])
          exec-bool-query-ast("big", [20.0])
          exec-bool-query-ast("big", [5.0])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "20" in l)
    assert any("false" in l for l in lines if "5"  in l)


def test_register_rule_calling_another_dynamic_rule(tmp_path):
    """A dynamic rule whose body calls another dynamic rule."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("base", ["ok"], [])
          register-rule-ast("derived", [["var", "X"]], [["call", "base", [["var", "X"]]]])
          exec-bool-query-ast("derived", ["ok"])
          exec-bool-query-ast("derived", ["no"])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "ok" in l)
    assert any("false" in l for l in lines if "no" in l)


# ── register-rule-ast multi-clause (OR semantics) ─────────────────────────────

def test_multiclauses_or_semantics(tmp_path):
    """Multiple clauses for the same predicate: at least one match = true."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("color", ["red"],  [])
          register-rule-ast("color", ["blue"], [])
          register-rule-ast("color", ["green"],[])
          exec-bool-query-ast("color", ["red"])
          exec-bool-query-ast("color", ["yellow"])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "red"    in l)
    assert any("false" in l for l in lines if "yellow" in l)


# ── exec-find-query-ast ───────────────────────────────────────────────────────

def test_exec_find_query_binds_vars(tmp_path):
    """exec-find-query-ast evaluates conditions and prints variable bindings."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          exec-find-query-ast([["var", "R"]], [["call", "str-concat", ["hello", " world", ["var", "R"]]]])
        query: setup()?
    """), tmp_path)
    assert "hello world" in stdout


# ── register-rule-ast with not-call condition ─────────────────────────────────

def test_register_rule_with_negation(tmp_path):
    """Rule body uses not-call (negation-as-failure)."""
    stdout = _run(textwrap.dedent("""\
        setup() if:
          register-rule-ast("is-bad", ["bad"], [])
          register-rule-ast("is-good", [["var", "X"]], [["not-call", "is-bad", [["var", "X"]]]])
          exec-bool-query-ast("is-good", ["nice"])
          exec-bool-query-ast("is-good", ["bad"])
        query: setup()?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "nice" in l)
    assert any("false" in l for l in lines if "bad"  in l)


# ── register-rule-ast with assert-fact condition ──────────────────────────────

def test_register_rule_with_assert_fact(tmp_path):
    """Dynamic rule body asserts a fact, then a compiled rule queries it."""
    stdout = _run(textwrap.dedent("""\
        do-register() if:
          register-rule-ast("store-it", [["var", "V"]], [["call", "assert-fact", ["dyn-subj", "dyn-pred", ["var", "V"]]]])
        run() if:
          do-register()
          exec-bool-query-ast("store-it", ["myvalue"])
        check(V) if:
          "dyn-subj"."dyn-pred" = V
        query: run()?
        query: check("myvalue")?
        query: check("other")?
    """), tmp_path)
    lines = stdout.splitlines()
    assert any("true"  in l for l in lines if "myvalue" in l and "check" in l)
    assert any("false" in l for l in lines if "other"   in l)
