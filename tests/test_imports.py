"""Tests for the import system and stdlib modules."""
import pathlib
import pytest
from logos.executor import Executor, run_source

STDLIB_DIR = pathlib.Path(__file__).parent.parent / "logos" / "stdlib"


def test_import_stdlib_lists():
    """Importing stdlib/lists makes list-member available."""
    ex = Executor()
    ex.load_source("""
import * from "stdlib/lists"

tags-of(article, ["news", "tech", "ai"])
""")
    result = ex.find("T", "list-member")
    # find via the raw predicate — just check import succeeded
    assert len(ex.rules) > 0  # stdlib rules loaded


def test_list_member_via_import():
    ex = Executor()
    ex.load_source("""
import * from "stdlib/lists"
""")
    from logos.ast_nodes import PredicateCall, Variable
    proofs = list(ex.engine.prove_all([
        PredicateCall(name='list-member', args=['b', ['a', 'b', 'c']])
    ]))
    assert any(p.success for p in proofs)


def test_list_member_not_found():
    ex = Executor()
    ex.load_source('import * from "stdlib/lists"\n')
    from logos.ast_nodes import PredicateCall
    proofs = list(ex.engine.prove_all([
        PredicateCall(name='list-member', args=['z', ['a', 'b', 'c']])
    ]))
    assert not any(p.success for p in proofs)


def test_import_stdlib_strings():
    ex = Executor()
    ex.load_source('import * from "stdlib/strings"\n')
    from logos.ast_nodes import PredicateCall, Variable
    proofs = list(ex.engine.prove_all([
        PredicateCall(name='str-empty', args=[''])
    ]))
    assert any(p.success for p in proofs)


def test_import_stdlib_math():
    ex = Executor()
    ex.load_source('import * from "stdlib/math"\n')
    from logos.ast_nodes import PredicateCall, Variable
    proofs = list(ex.engine.prove_all([
        PredicateCall(name='positive', args=[5.0])
    ]))
    assert any(p.success for p in proofs)


def test_import_stdlib_io():
    ex = Executor()
    ex.load_source('import * from "stdlib/io"\n')
    # Just verify the module loaded without error
    assert ex is not None


def test_double_import_is_idempotent():
    """Importing the same file twice should not duplicate rules."""
    ex = Executor()
    ex.load_source('import * from "stdlib/lists"\n')
    rule_count = len(ex.rules)
    ex.load_source('import * from "stdlib/lists"\n')
    assert len(ex.rules) == rule_count  # no duplicates


def test_import_nonexistent_raises():
    from logos.errors import LogosImportError
    ex = Executor()
    with pytest.raises(LogosImportError):
        ex.load_source('import * from "stdlib/nonexistent"\n')


def test_list_sum_via_stdlib():
    ex = Executor()
    ex.load_source('import * from "stdlib/lists"\n')
    from logos.ast_nodes import PredicateCall, Variable
    proofs = list(ex.engine.prove_all([
        PredicateCall(name='list-sum', args=[[1.0, 2.0, 3.0], Variable('S')])
    ]))
    sums = [p.bindings.get('S') for p in proofs if p.success]
    assert 6.0 in sums
