"""
Integration tests for the Logos compilation backend (Phases H–K).

The fixture compiles examples/02_voting_rules.logos to a temporary binary
and the tests verify the binary's output matches expected behaviour.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from logos.codegen import Compiler
from logos.compiler import CompilationError, compile_file
from logos.parser import parse_file

LOGOS_DIR   = Path(__file__).parent.parent
EXAMPLES_DIR = LOGOS_DIR / "examples"
VOTING_FILE  = str(EXAMPLES_DIR / "02_voting_rules.logos")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def voting_binary(tmp_path_factory):
    """Compile 02_voting_rules.logos once per test session."""
    tmp = tmp_path_factory.mktemp("binaries")
    out = str(tmp / "voting")
    compile_file(VOTING_FILE, out)
    return out


# ── Binary existence and exit code ────────────────────────────────────────────

def test_voting_binary_exists(voting_binary):
    assert os.path.isfile(voting_binary)
    assert os.access(voting_binary, os.X_OK)


def test_voting_exit_code(voting_binary):
    result = subprocess.run([voting_binary], capture_output=True, text=True)
    assert result.returncode == 0


# ── Boolean query outputs ─────────────────────────────────────────────────────

def test_voting_alice_true(voting_binary):
    result = subprocess.run([voting_binary], capture_output=True, text=True)
    assert "can-vote(alice)" in result.stdout
    assert "true" in result.stdout


def test_voting_bob_false(voting_binary):
    result = subprocess.run([voting_binary], capture_output=True, text=True)
    assert "can-vote(bob)" in result.stdout
    # bob is 17 → fails age check → false
    lines = [l for l in result.stdout.splitlines() if "can-vote(bob)" in l]
    assert lines, "no can-vote(bob) line in output"
    assert "false" in lines[0]


def test_voting_carol_false(voting_binary):
    result = subprocess.run([voting_binary], capture_output=True, text=True)
    assert "can-vote(carol)" in result.stdout
    lines = [l for l in result.stdout.splitlines() if "can-vote(carol)" in l]
    assert lines, "no can-vote(carol) line in output"
    assert "false" in lines[0]


# ── Find query output ─────────────────────────────────────────────────────────

def test_voting_find_alice(voting_binary):
    result = subprocess.run([voting_binary], capture_output=True, text=True)
    # Only alice satisfies can-vote; bob and carol must not appear as find results
    find_lines = [
        l for l in result.stdout.splitlines()
        if "P=" in l  # find-row lines contain "P=<name>"
    ]
    assert find_lines, "no find-query rows in output"
    names = [l.split("P=")[1].split()[0].rstrip(",") for l in find_lines]
    assert "alice" in names
    assert "bob"   not in names
    assert "carol" not in names


# ── Generated C readability ───────────────────────────────────────────────────

def test_generated_c_readable(tmp_path):
    """keep_c=True: generated C file contains expected markers."""
    out = str(tmp_path / "voting")
    compile_file(VOTING_FILE, out, keep_c=True)
    c_text = open(out + ".c").read()
    assert "logos_setup"        in c_text
    assert "logos_graph_assert" in c_text
    assert "pred_can_vote"      in c_text
    assert "rule_can_vote_0"    in c_text


# ── CLI subcommand ────────────────────────────────────────────────────────────

def test_compile_cli(tmp_path):
    """logos compile <file> works end-to-end via the CLI."""
    out = str(tmp_path / "voting_cli")
    result = subprocess.run(
        [sys.executable, "-m", "logos", "compile", VOTING_FILE, "-o", out],
        capture_output=True,
        text=True,
        cwd=str(LOGOS_DIR),
    )
    assert result.returncode == 0, (
        f"CLI compile failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert os.path.isfile(out), "binary not created by CLI"
    assert "Compiled:" in result.stdout


# ── Codegen unit tests ────────────────────────────────────────────────────────

def test_codegen_generates_c_string():
    program  = parse_file(VOTING_FILE)
    c_source = Compiler(program).generate()
    assert isinstance(c_source, str)
    assert len(c_source) > 500


def test_codegen_ignores_import_stmts():
    """Compiler silently skips ImportStmt nodes (resolve_imports handles them)."""
    from logos.parser import parse
    prog = parse('import foo from "bar.logos"')
    # Should not raise — imports are flattened before Compiler runs
    c_source = Compiler(prog).generate()
    assert isinstance(c_source, str)


def test_missing_import_raises(tmp_path):
    """compile_file raises CompilationError when an imported file is missing."""
    f = tmp_path / "test.logos"
    f.write_text('import * from "nonexistent.logos"\n')
    with pytest.raises(CompilationError, match="Import not found"):
        compile_file(str(f), str(tmp_path / "out"))
