"""Tests for Phase B native primitives."""
import pytest
from logos.executor import run_source, Executor
from logos.ast_nodes import Variable
from logos.inference import InferenceEngine
from logos.semantic_graph import SemanticGraph
from logos.confidence import ConfidenceValue


def V(name: str) -> Variable:
    """Shorthand for creating a Variable."""
    return Variable(name=name)


def query_primitive(predicate, *args):
    """Run a single primitive predicate call; return list of binding dicts.
    Pass V("Name") for unbound output variables, plain values for literals.
    """
    from logos.ast_nodes import PredicateCall
    eng = InferenceEngine(SemanticGraph(), [])
    goal = PredicateCall(name=predicate, args=list(args))
    return [p.bindings for p in eng.prove(goal) if p.success]


# ── String primitives ─────────────────────────────────────────────────────────

def test_str_concat_bound():
    results = query_primitive("str-concat", "hello", " world", V("Result"))
    assert len(results) == 1
    assert results[0]["Result"] == "hello world"


def test_str_concat_verifies():
    results = query_primitive("str-concat", "hello", " world", "hello world")
    assert len(results) == 1


def test_str_concat_fails():
    results = query_primitive("str-concat", "hello", " world", "wrong")
    assert len(results) == 0


def test_str_length():
    results = query_primitive("str-length", "hello", V("Len"))
    assert len(results) == 1
    assert results[0]["Len"] == 5.0


def test_str_length_empty():
    results = query_primitive("str-length", "", V("Len"))
    assert results[0]["Len"] == 0.0


def test_str_char_at():
    results = query_primitive("str-char-at", "hello", 1.0, V("Ch"))
    assert results[0]["Ch"] == "e"


def test_str_char_at_out_of_bounds():
    results = query_primitive("str-char-at", "hello", 10.0, V("Ch"))
    assert results == []


def test_str_starts_with_true():
    results = query_primitive("str-starts-with", "hello world", "hello")
    assert len(results) == 1


def test_str_starts_with_false():
    results = query_primitive("str-starts-with", "hello world", "world")
    assert len(results) == 0


def test_str_ends_with_true():
    results = query_primitive("str-ends-with", "hello world", "world")
    assert len(results) == 1


def test_str_slice():
    results = query_primitive("str-slice", "hello world", 6.0, 11.0, V("R"))
    assert results[0]["R"] == "world"


def test_str_to_number():
    results = query_primitive("str-to-number", "3.14", V("N"))
    assert abs(results[0]["N"] - 3.14) < 1e-9


def test_str_to_number_invalid():
    results = query_primitive("str-to-number", "abc", V("N"))
    assert results == []


def test_number_to_str_int():
    results = query_primitive("number-to-str", 42.0, V("S"))
    assert results[0]["S"] == "42"


def test_number_to_str_float():
    results = query_primitive("number-to-str", 3.14, V("S"))
    assert results[0]["S"] == "3.14"


def test_str_split():
    results = query_primitive("str-split", "a,b,c", ",", V("L"))
    assert results[0]["L"] == ["a", "b", "c"]


def test_str_split_chars():
    results = query_primitive("str-split", "abc", "", V("L"))
    assert results[0]["L"] == ["a", "b", "c"]


def test_str_join():
    results = query_primitive("str-join", ["a", "b", "c"], ",", V("R"))
    assert results[0]["R"] == "a,b,c"


def test_str_contains_true():
    results = query_primitive("str-contains", "hello world", "world")
    assert len(results) == 1


def test_str_contains_false():
    results = query_primitive("str-contains", "hello", "xyz")
    assert len(results) == 0


def test_str_upper():
    results = query_primitive("str-upper", "hello", V("U"))
    assert results[0]["U"] == "HELLO"


def test_str_lower():
    results = query_primitive("str-lower", "HELLO", V("L"))
    assert results[0]["L"] == "hello"


def test_str_trim():
    results = query_primitive("str-trim", "  hello  ", V("T"))
    assert results[0]["T"] == "hello"


# ── Character class predicates ────────────────────────────────────────────────

def test_char_alpha_letter():
    results = query_primitive("char-alpha", "a")
    assert len(results) == 1


def test_char_alpha_digit():
    results = query_primitive("char-alpha", "1")
    assert len(results) == 0


def test_char_alpha_space():
    results = query_primitive("char-alpha", " ")
    assert len(results) == 0


def test_char_digit_true():
    results = query_primitive("char-digit", "5")
    assert len(results) == 1


def test_char_digit_false():
    results = query_primitive("char-digit", "a")
    assert len(results) == 0


def test_char_whitespace_space():
    results = query_primitive("char-whitespace", " ")
    assert len(results) == 1


def test_char_whitespace_tab():
    results = query_primitive("char-whitespace", "\t")
    assert len(results) == 1


def test_char_whitespace_letter():
    results = query_primitive("char-whitespace", "a")
    assert len(results) == 0


def test_char_code():
    results = query_primitive("char-code", "A", V("Code"))
    assert len(results) == 1
    assert results[0]["Code"] == 65.0


# ── List primitives ───────────────────────────────────────────────────────────

def test_list_head():
    results = query_primitive("list-head", [1, 2, 3], V("H"))
    assert results[0]["H"] == 1


def test_list_head_empty_fails():
    results = query_primitive("list-head", [], V("H"))
    assert results == []


def test_list_tail():
    results = query_primitive("list-tail", [1, 2, 3], V("T"))
    assert results[0]["T"] == [2, 3]


def test_list_tail_empty():
    results = query_primitive("list-tail", [], V("T"))
    assert results[0]["T"] == []


def test_list_cons_build():
    results = query_primitive("list-cons", 1, [2, 3], V("L"))
    assert results[0]["L"] == [1, 2, 3]


def test_list_cons_decompose():
    results = query_primitive("list-cons", V("H"), V("T"), [1, 2, 3])
    assert results[0]["H"] == 1
    assert results[0]["T"] == [2, 3]


def test_list_empty_true():
    results = query_primitive("list-empty", [])
    assert len(results) == 1


def test_list_empty_false():
    results = query_primitive("list-empty", [1, 2])
    assert len(results) == 0


def test_list_length():
    results = query_primitive("list-length", [1, 2, 3], V("L"))
    assert results[0]["L"] == 3.0


def test_list_nth():
    results = query_primitive("list-nth", ["a", "b", "c"], 1.0, V("E"))
    assert results[0]["E"] == "b"


def test_list_append():
    results = query_primitive("list-append", [1, 2], [3, 4], V("R"))
    assert results[0]["R"] == [1, 2, 3, 4]


def test_list_reverse():
    results = query_primitive("list-reverse", [1, 2, 3], V("R"))
    assert results[0]["R"] == [3, 2, 1]


def test_list_flatten():
    results = query_primitive("list-flatten", [[1, 2], [3], [4, 5]], V("F"))
    assert results[0]["F"] == [1, 2, 3, 4, 5]


# ── Arithmetic primitives ─────────────────────────────────────────────────────

def test_num_add():
    results = query_primitive("num-add", 3.0, 4.0, V("C"))
    assert results[0]["C"] == 7.0


def test_num_sub():
    results = query_primitive("num-sub", 10.0, 3.0, V("C"))
    assert results[0]["C"] == 7.0


def test_num_mul():
    results = query_primitive("num-mul", 3.0, 4.0, V("C"))
    assert results[0]["C"] == 12.0


def test_num_div():
    results = query_primitive("num-div", 10.0, 4.0, V("C"))
    assert results[0]["C"] == 2.5


def test_num_div_zero():
    results = query_primitive("num-div", 10.0, 0.0, V("C"))
    assert results == []


def test_num_mod():
    results = query_primitive("num-mod", 10.0, 3.0, V("C"))
    assert results[0]["C"] == 1.0


def test_num_abs():
    results = query_primitive("num-abs", -5.0, V("B"))
    assert results[0]["B"] == 5.0


def test_num_floor():
    results = query_primitive("num-floor", 3.7, V("B"))
    assert results[0]["B"] == 3.0


def test_num_ceil():
    results = query_primitive("num-ceil", 3.2, V("B"))
    assert results[0]["B"] == 4.0


def test_num_min():
    results = query_primitive("num-min", 3.0, 7.0, V("C"))
    assert results[0]["C"] == 3.0


def test_num_max():
    results = query_primitive("num-max", 3.0, 7.0, V("C"))
    assert results[0]["C"] == 7.0


# ── Meta predicates ───────────────────────────────────────────────────────────

def test_equal_unifies():
    results = query_primitive("equal", V("X"), "hello")
    assert results[0]["X"] == "hello"


def test_equal_verifies():
    results = query_primitive("equal", "hello", "hello")
    assert len(results) == 1


def test_not_equal():
    results = query_primitive("not-equal", "a", "b")
    assert len(results) == 1
    results2 = query_primitive("not-equal", "a", "a")
    assert len(results2) == 0


def test_ground_true():
    results = query_primitive("ground", "hello")
    assert len(results) == 1


def test_ground_false():
    results = query_primitive("ground", V("X"))
    assert len(results) == 0


# ── Integration: primitives in Logos rules ────────────────────────────────────

def test_rule_using_str_concat():
    from logos.ast_nodes import PredicateCall
    ex = run_source("""
name-of of alice := "Alice"

greeting(P, G) if:
  name-of(P, N)
  str-concat("Hello, ", N, G)
""")
    results = list(ex.engine.prove_all([
        PredicateCall(name='greeting', args=['alice', V('G')])
    ]))
    greetings = [r.bindings.get('G') for r in results if r.success]
    assert "Hello, Alice" in greetings


def test_rule_using_list_primitives():
    """Rules using list-head and list-tail primitives via inference rules."""
    from logos.ast_nodes import PredicateCall
    ex = run_source("""
tags-of of article := ["news", "tech", "ai"]

first-tag(Item, Tag) if:
  tags-of(Item, Tags)
  list-head(Tags, Tag)
""")
    results = list(ex.engine.prove_all([
        PredicateCall(name='first-tag', args=['article', V('Tag')])
    ]))
    tags = [r.bindings.get('Tag') for r in results if r.success]
    assert "news" in tags


def test_assert_fact_primitive():
    from logos.ast_nodes import PredicateCall
    ex = run_source("""
setup(S, P, Val) if:
  assert-fact(S, P, Val)
""")
    list(ex.engine.prove(
        PredicateCall(name='setup', args=['bob', 'role', 'admin'])
    ))
    result = ex.graph.query('bob', 'role')
    assert result.found
    assert result.value == 'admin'


def test_retract_fact_primitive():
    from logos.ast_nodes import PredicateCall
    ex = run_source("""
age of alice := 30
""")
    assert ex.graph.query('alice', 'age').found
    list(ex.engine.prove(
        PredicateCall(name='retract-fact', args=['alice', 'age'])
    ))
    assert not ex.graph.query('alice', 'age').found


# ── Cycle detection ───────────────────────────────────────────────────────────

def test_cycle_detection():
    from logos.errors import CycleDetectedError
    from logos.ast_nodes import PredicateCall
    ex = run_source("""
loop(X) if:
  loop(X)
""")
    with pytest.raises(CycleDetectedError):
        list(ex.engine.prove(PredicateCall(name='loop', args=['test'])))
