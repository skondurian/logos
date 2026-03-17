"""
Phase 1 tests: list type + import flattening.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from logos.codegen import Compiler
from logos.compiler import CompilationError, compile_file, resolve_imports
from logos.parser import parse, parse_file

LOGOS_DIR = Path(__file__).parent.parent


# ── resolve_imports ───────────────────────────────────────────────────────────

def test_resolve_imports_identity(tmp_path):
    """A file with no imports is returned unchanged."""
    f = tmp_path / "a.logos"
    f.write_text("age of alice := 30 years\n")
    prog = parse_file(str(f))
    flat = resolve_imports(prog, str(tmp_path))
    assert len(flat.statements) == len(prog.statements)


def test_resolve_imports_flattens(tmp_path):
    """Imported file's statements are spliced in."""
    helper = tmp_path / "helper.logos"
    helper.write_text("name of bob := \"Bob\"\n")

    main = tmp_path / "main.logos"
    main.write_text(f'import * from "helper.logos"\nname of alice := "Alice"\n')

    prog = parse_file(str(main))
    flat = resolve_imports(prog, str(tmp_path))

    # Should have 2 SemanticBindings, 0 ImportStmts
    from logos.ast_nodes import SemanticBinding, ImportStmt
    stmts = flat.statements
    assert not any(isinstance(s, ImportStmt) for s in stmts)
    assert sum(1 for s in stmts if isinstance(s, SemanticBinding)) == 2


def test_resolve_imports_deduplicates(tmp_path):
    """The same file imported twice is only inlined once."""
    lib = tmp_path / "lib.logos"
    lib.write_text("name of x := \"x\"\n")

    a = tmp_path / "a.logos"
    a.write_text(f'import * from "lib.logos"\nname of a := "a"\n')
    b = tmp_path / "b.logos"
    b.write_text(f'import * from "lib.logos"\nname of b := "b"\n')

    main = tmp_path / "main.logos"
    main.write_text(f'import * from "a.logos"\nimport * from "b.logos"\n')

    prog = parse_file(str(main))
    flat = resolve_imports(prog, str(tmp_path))

    from logos.ast_nodes import SemanticBinding
    names = [s.path.parts[1] if len(s.path.parts) > 1 else s.path.parts[0]
             for s in flat.statements
             if isinstance(s, SemanticBinding)]
    # "x" should appear exactly once even though lib.logos was imported twice
    assert names.count("name") == 3   # x, a, b


def test_resolve_imports_missing_raises(tmp_path):
    main = tmp_path / "main.logos"
    main.write_text('import * from "does_not_exist.logos"\n')
    prog = parse_file(str(main))
    with pytest.raises(CompilationError, match="Import not found"):
        resolve_imports(prog, str(tmp_path))


def test_resolve_imports_circular_raises(tmp_path):
    a = tmp_path / "a.logos"
    b = tmp_path / "b.logos"
    a.write_text('import * from "b.logos"\n')
    b.write_text('import * from "a.logos"\n')
    prog = parse_file(str(a))
    with pytest.raises(CompilationError, match="[Cc]ircular"):
        resolve_imports(prog, str(tmp_path))


# ── ListLit in codegen ────────────────────────────────────────────────────────

def test_list_fact_generates_list_cons():
    """A ListLit fact value emits logos_list_cons calls."""
    prog     = parse('items := ["a", "b", "c"]\n')
    c_source = Compiler(prog).generate()
    assert "logos_list_cons" in c_source
    assert "logos_nil()"     in c_source


def test_empty_list_fact_generates_nil():
    prog     = parse("items := []\n")
    c_source = Compiler(prog).generate()
    assert "logos_nil()" in c_source
    # No logos_list_cons needed for empty list
    assert "logos_list_cons" not in c_source


def test_nested_list_fact():
    prog     = parse('matrix := [["a", "b"], ["c", "d"]]\n')
    c_source = Compiler(prog).generate()
    assert c_source.count("logos_list_cons") >= 6  # 2 inner + 2 outer + outer pair


# ── List term compilation round-trip ─────────────────────────────────────────

def test_list_fact_compiles_and_runs(tmp_path):
    """A file containing a list fact compiles to a binary that exits 0."""
    src = tmp_path / "test.logos"
    src.write_text('items := ["hello", "world"]\n')
    out = str(tmp_path / "bin")
    compile_file(str(src), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0


# ── Import flattening end-to-end ──────────────────────────────────────────────

def test_import_compile_and_run(tmp_path):
    """A file that imports another compiles and produces correct output."""
    helper = tmp_path / "facts.logos"
    helper.write_text(textwrap.dedent("""\
        age of alice := 30 years
          confidence: absolute
        citizenship of alice := "US"
          confidence: absolute
    """))

    rule_file = tmp_path / "rules.logos"
    rule_file.write_text(textwrap.dedent(f"""\
        import * from "facts.logos"

        can-vote(P) if:
          P.age >= 18 years
          P.citizenship = "US"

        query: can-vote(alice)?
    """))

    out = str(tmp_path / "bin")
    compile_file(str(rule_file), out)
    result = subprocess.run([out], capture_output=True, text=True)
    assert result.returncode == 0
    assert "true" in result.stdout


# ── stdlib/lists import survives flattening (no primitives yet) ───────────────

def test_lists_stdlib_flattens_without_error(tmp_path):
    """stdlib/lists.logos can be imported and flattened (predicates become rules)."""
    lists_path = LOGOS_DIR / "logos" / "stdlib" / "lists.logos"
    if not lists_path.exists():
        pytest.skip("stdlib/lists.logos not found")

    driver = tmp_path / "driver.logos"
    driver.write_text(f'import * from "{lists_path}"\n')

    prog = parse_file(str(driver))
    flat = resolve_imports(prog, str(tmp_path))
    # Just check the AST flattened without error and has rules
    from logos.ast_nodes import InferenceRule
    assert any(isinstance(s, InferenceRule) for s in flat.statements)
