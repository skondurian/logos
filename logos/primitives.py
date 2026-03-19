"""
Native primitive predicates for Logos — Phase B of the self-hosting roadmap.

Primitives are Python callables registered by name. The InferenceEngine
tries the primitive registry before SLD-resolution, so any registered name
can be used directly in Logos rules and queries.

Primitive signature:
    fn(args, bindings, engine) -> Iterator[Proof]

Where:
    args     — list of args from the PredicateCall, with bindings already
               applied by the caller
    bindings — current variable bindings dict
    engine   — the InferenceEngine instance (for graph access)
"""

from __future__ import annotations
from typing import Any, Iterator, TYPE_CHECKING

from logos.ast_nodes import Variable
from logos.confidence import ConfidenceValue

if TYPE_CHECKING:
    from logos.inference import InferenceEngine, Proof

# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, Any] = {}


def primitive(name: str):
    """Decorator to register a function as a named primitive predicate."""
    def decorator(fn):
        REGISTRY[name] = fn
        return fn
    return decorator


# ── Internal helpers ──────────────────────────────────────────────────────────

def _proof(bindings: dict) -> "Proof":
    from logos.inference import Proof
    return Proof(success=True, bindings=bindings,
                 confidence=ConfidenceValue.absolute())


def _unify(var_or_val: Any, value: Any, bindings: dict) -> "dict | None":
    """Unify an output position with a computed value."""
    from logos.inference import unify_term
    return unify_term(var_or_val, value, bindings)


def _is_ground(x: Any) -> bool:
    """Return True if x is a fully-ground (non-Variable) value."""
    return not isinstance(x, Variable)


# ── String primitives ─────────────────────────────────────────────────────────

@primitive("str-concat")
def prim_str_concat(args, bindings, engine):
    """str-concat(A, B, Result) — Result = A ++ B"""
    if len(args) != 3:
        return
    a, b, result = args
    if isinstance(a, str) and isinstance(b, str):
        new_b = _unify(result, a + b, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-length")
def prim_str_length(args, bindings, engine):
    """str-length(Str, Len) — Len = len(Str)"""
    if len(args) != 2:
        return
    s, length = args
    if isinstance(s, str):
        new_b = _unify(length, float(len(s)), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-char-at")
def prim_str_char_at(args, bindings, engine):
    """str-char-at(Str, Idx, Char) — Char = Str[Idx]"""
    if len(args) != 3:
        return
    s, idx, char = args
    if isinstance(s, str) and isinstance(idx, (int, float)):
        i = int(idx)
        if 0 <= i < len(s):
            new_b = _unify(char, s[i], bindings)
            if new_b is not None:
                yield _proof(new_b)


@primitive("str-starts-with")
def prim_str_starts_with(args, bindings, engine):
    """str-starts-with(Str, Prefix) — succeeds if Str starts with Prefix"""
    if len(args) != 2:
        return
    s, prefix = args
    if isinstance(s, str) and isinstance(prefix, str):
        if s.startswith(prefix):
            yield _proof(bindings)


@primitive("str-ends-with")
def prim_str_ends_with(args, bindings, engine):
    """str-ends-with(Str, Suffix) — succeeds if Str ends with Suffix"""
    if len(args) != 2:
        return
    s, suffix = args
    if isinstance(s, str) and isinstance(suffix, str):
        if s.endswith(suffix):
            yield _proof(bindings)


@primitive("str-slice")
def prim_str_slice(args, bindings, engine):
    """str-slice(Str, Start, End, Result) — Result = Str[Start:End]"""
    if len(args) != 4:
        return
    s, start, end, result = args
    if (isinstance(s, str) and isinstance(start, (int, float))
            and isinstance(end, (int, float))):
        sliced = s[int(start):int(end)]
        new_b = _unify(result, sliced, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-to-number")
def prim_str_to_number(args, bindings, engine):
    """str-to-number(Str, Num) — Num = float(Str)"""
    if len(args) != 2:
        return
    s, num = args
    if isinstance(s, str):
        try:
            n = float(s)
            new_b = _unify(num, n, bindings)
            if new_b is not None:
                yield _proof(new_b)
        except ValueError:
            pass


@primitive("number-to-str")
def prim_number_to_str(args, bindings, engine):
    """number-to-str(Num, Str) — Str = str(Num)"""
    if len(args) != 2:
        return
    num, s = args
    if isinstance(num, (int, float)):
        # Avoid "30.0" when the number is integral
        val = str(int(num)) if num == int(num) else str(num)
        new_b = _unify(s, val, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-split")
def prim_str_split(args, bindings, engine):
    """str-split(Str, Sep, List) — splits Str by Sep into List.
    If Sep is empty string, splits into individual characters."""
    if len(args) != 3:
        return
    s, sep, lst = args
    if isinstance(s, str) and isinstance(sep, str):
        parts = list(s) if sep == "" else s.split(sep)
        new_b = _unify(lst, parts, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-join")
def prim_str_join(args, bindings, engine):
    """str-join(List, Sep, Result) — Result = Sep.join(List)"""
    if len(args) != 3:
        return
    lst, sep, result = args
    if isinstance(lst, list) and isinstance(sep, str):
        if all(isinstance(x, str) for x in lst):
            new_b = _unify(result, sep.join(lst), bindings)
            if new_b is not None:
                yield _proof(new_b)


@primitive("str-upper")
def prim_str_upper(args, bindings, engine):
    """str-upper(Str, Upper) — Upper = Str.upper()"""
    if len(args) != 2:
        return
    s, upper = args
    if isinstance(s, str):
        new_b = _unify(upper, s.upper(), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-lower")
def prim_str_lower(args, bindings, engine):
    """str-lower(Str, Lower) — Lower = Str.lower()"""
    if len(args) != 2:
        return
    s, lower = args
    if isinstance(s, str):
        new_b = _unify(lower, s.lower(), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-trim")
def prim_str_trim(args, bindings, engine):
    """str-trim(Str, Trimmed) — Trimmed = Str.strip()"""
    if len(args) != 2:
        return
    s, trimmed = args
    if isinstance(s, str):
        new_b = _unify(trimmed, s.strip(), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("str-contains")
def prim_str_contains(args, bindings, engine):
    """str-contains(Str, Sub) — succeeds if Sub is in Str"""
    if len(args) != 2:
        return
    s, sub = args
    if isinstance(s, str) and isinstance(sub, str):
        if sub in s:
            yield _proof(bindings)


# ── Character class predicates ────────────────────────────────────────────────

@primitive("char-alpha")
def prim_char_alpha(args, bindings, engine):
    """char-alpha(C) — succeeds iff C is an alphabetic character"""
    if len(args) != 1:
        return
    c = args[0]
    if isinstance(c, str) and len(c) == 1 and c.isalpha():
        yield _proof(bindings)


@primitive("char-digit")
def prim_char_digit(args, bindings, engine):
    """char-digit(C) — succeeds iff C is a digit character"""
    if len(args) != 1:
        return
    c = args[0]
    if isinstance(c, str) and len(c) == 1 and c.isdigit():
        yield _proof(bindings)


@primitive("char-whitespace")
def prim_char_whitespace(args, bindings, engine):
    """char-whitespace(C) — succeeds iff C is whitespace"""
    if len(args) != 1:
        return
    c = args[0]
    if isinstance(c, str) and len(c) == 1 and c.isspace():
        yield _proof(bindings)


@primitive("char-alnum")
def prim_char_alnum(args, bindings, engine):
    """char-alnum(C) — succeeds iff C is alphanumeric"""
    if len(args) != 1:
        return
    c = args[0]
    if isinstance(c, str) and len(c) == 1 and c.isalnum():
        yield _proof(bindings)


@primitive("char-code")
def prim_char_code(args, bindings, engine):
    """char-code(Char, Code) — Code = ord(Char)"""
    if len(args) != 2:
        return
    char, code = args
    if isinstance(char, str) and len(char) == 1:
        new_b = _unify(code, float(ord(char)), bindings)
        if new_b is not None:
            yield _proof(new_b)


# ── List primitives ───────────────────────────────────────────────────────────

@primitive("list-head")
def prim_list_head(args, bindings, engine):
    """list-head(List, Head) — Head = List[0], fails if List is empty"""
    if len(args) != 2:
        return
    lst, head = args
    if isinstance(lst, list) and lst:
        new_b = _unify(head, lst[0], bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("list-tail")
def prim_list_tail(args, bindings, engine):
    """list-tail(List, Tail) — Tail = List[1:]"""
    if len(args) != 2:
        return
    lst, tail = args
    if isinstance(lst, list):
        new_b = _unify(tail, lst[1:], bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("list-cons")
def prim_list_cons(args, bindings, engine):
    """list-cons(Head, Tail, List) — bidirectional: build or decompose.

    Build:  Head + Tail given → List = [Head] + Tail
    Decompose: List given → Head = List[0], Tail = List[1:]
    """
    if len(args) != 3:
        return
    head, tail, lst = args

    if _is_ground(head) and _is_ground(tail):
        # Build mode
        if isinstance(tail, list):
            new_b = _unify(lst, [head] + tail, bindings)
            if new_b is not None:
                yield _proof(new_b)
    elif _is_ground(lst):
        # Decompose mode
        if isinstance(lst, list) and lst:
            new_b = _unify(head, lst[0], bindings)
            if new_b is not None:
                new_b2 = _unify(tail, lst[1:], new_b)
                if new_b2 is not None:
                    yield _proof(new_b2)
    elif _is_ground(head) and _is_ground(lst):
        # Head and list known → derive tail
        if isinstance(lst, list) and lst and lst[0] == head:
            new_b = _unify(tail, lst[1:], bindings)
            if new_b is not None:
                yield _proof(new_b)


@primitive("list-empty")
def prim_list_empty(args, bindings, engine):
    """list-empty(List) — succeeds iff List = []"""
    if len(args) != 1:
        return
    lst = args[0]
    if isinstance(lst, list) and not lst:
        yield _proof(bindings)


@primitive("list-length")
def prim_list_length(args, bindings, engine):
    """list-length(List, Len) — Len = len(List)"""
    if len(args) != 2:
        return
    lst, length = args
    if isinstance(lst, list):
        new_b = _unify(length, float(len(lst)), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("list-nth")
def prim_list_nth(args, bindings, engine):
    """list-nth(List, N, Elem) — Elem = List[N] (0-indexed)"""
    if len(args) != 3:
        return
    lst, n, elem = args
    if isinstance(lst, list) and isinstance(n, (int, float)):
        i = int(n)
        if 0 <= i < len(lst):
            new_b = _unify(elem, lst[i], bindings)
            if new_b is not None:
                yield _proof(new_b)


@primitive("list-append")
def prim_list_append(args, bindings, engine):
    """list-append(List1, List2, Result) — Result = List1 ++ List2"""
    if len(args) != 3:
        return
    lst1, lst2, result = args
    if isinstance(lst1, list) and isinstance(lst2, list):
        new_b = _unify(result, lst1 + lst2, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("list-reverse")
def prim_list_reverse(args, bindings, engine):
    """list-reverse(List, Rev) — Rev = reversed(List)"""
    if len(args) != 2:
        return
    lst, rev = args
    if isinstance(lst, list):
        new_b = _unify(rev, list(reversed(lst)), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("list-flatten")
def prim_list_flatten(args, bindings, engine):
    """list-flatten(List, Flat) — Flat = one-level flattened List"""
    if len(args) != 2:
        return
    lst, flat = args
    if isinstance(lst, list):
        result = []
        for item in lst:
            if isinstance(item, list):
                result.extend(item)
            else:
                result.append(item)
        new_b = _unify(flat, result, bindings)
        if new_b is not None:
            yield _proof(new_b)


# ── Arithmetic predicates ─────────────────────────────────────────────────────

@primitive("num-add")
def prim_num_add(args, bindings, engine):
    """num-add(A, B, C) — C = A + B"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        new_b = _unify(c, a + b, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-sub")
def prim_num_sub(args, bindings, engine):
    """num-sub(A, B, C) — C = A - B"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        new_b = _unify(c, a - b, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-mul")
def prim_num_mul(args, bindings, engine):
    """num-mul(A, B, C) — C = A * B"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        new_b = _unify(c, a * b, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-div")
def prim_num_div(args, bindings, engine):
    """num-div(A, B, C) — C = A / B (fails if B = 0)"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0:
        new_b = _unify(c, a / b, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-mod")
def prim_num_mod(args, bindings, engine):
    """num-mod(A, B, C) — C = A % B"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0:
        new_b = _unify(c, a % b, bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-abs")
def prim_num_abs(args, bindings, engine):
    """num-abs(A, B) — B = abs(A)"""
    if len(args) != 2:
        return
    a, b = args
    if isinstance(a, (int, float)):
        new_b = _unify(b, abs(a), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-floor")
def prim_num_floor(args, bindings, engine):
    """num-floor(A, B) — B = floor(A)"""
    if len(args) != 2:
        return
    import math
    a, b = args
    if isinstance(a, (int, float)):
        new_b = _unify(b, float(math.floor(a)), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-ceil")
def prim_num_ceil(args, bindings, engine):
    """num-ceil(A, B) — B = ceil(A)"""
    if len(args) != 2:
        return
    import math
    a, b = args
    if isinstance(a, (int, float)):
        new_b = _unify(b, float(math.ceil(a)), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-min")
def prim_num_min(args, bindings, engine):
    """num-min(A, B, C) — C = min(A, B)"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        new_b = _unify(c, min(a, b), bindings)
        if new_b is not None:
            yield _proof(new_b)


@primitive("num-max")
def prim_num_max(args, bindings, engine):
    """num-max(A, B, C) — C = max(A, B)"""
    if len(args) != 3:
        return
    a, b, c = args
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        new_b = _unify(c, max(a, b), bindings)
        if new_b is not None:
            yield _proof(new_b)


# ── IO primitives ─────────────────────────────────────────────────────────────

@primitive("read-file")
def prim_read_file(args, bindings, engine):
    """read-file(Path, Content) — reads file at Path into Content string"""
    if len(args) != 2:
        return
    path, content = args
    if isinstance(path, str):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            new_b = _unify(content, text, bindings)
            if new_b is not None:
                yield _proof(new_b)
        except OSError:
            pass


@primitive("argv")
def prim_argv(args, bindings, engine):
    """argv(N, Value) — Value = sys.argv[N] (0-based); fails if out of range"""
    import sys
    if len(args) != 2:
        return
    n, value = args
    if not isinstance(n, (int, float)):
        return
    idx = int(n)
    if idx < 0 or idx >= len(sys.argv):
        return
    new_b = _unify(value, sys.argv[idx], bindings)
    if new_b is not None:
        yield _proof(new_b)


@primitive("argc")
def prim_argc(args, bindings, engine):
    """argc(N) — N = len(sys.argv)"""
    import sys
    if len(args) != 1:
        return
    new_b = _unify(args[0], float(len(sys.argv)), bindings)
    if new_b is not None:
        yield _proof(new_b)


@primitive("lex-file")
def prim_lex_file(args, bindings, engine):
    """lex-file(Path, Tokens) — reads and tokenizes a .logos file.
    Tokens is a list of [type, value] pairs including INDENT/DEDENT."""
    if len(args) != 2:
        return
    path, tokens_out = args
    if not isinstance(path, str):
        return
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return
    from logos.lexer import tokenize
    toks = tokenize(source)
    tok_list = [[t.type, t.value] for t in toks]
    new_b = _unify(tokens_out, tok_list, bindings)
    if new_b is not None:
        yield _proof(new_b)


@primitive("lex-source")
def prim_lex_source(args, bindings, engine):
    """lex-source(Source, Tokens) — tokenizes a Logos source string.
    Tokens is a list of [type, value] pairs including INDENT/DEDENT."""
    if len(args) != 2:
        return
    source, tokens_out = args
    if not isinstance(source, str):
        return
    from logos.lexer import tokenize
    toks = tokenize(source)
    tok_list = [[t.type, t.value] for t in toks]
    new_b = _unify(tokens_out, tok_list, bindings)
    if new_b is not None:
        yield _proof(new_b)


@primitive("write-output")
def prim_write_output(args, bindings, engine):
    """write-output(Text) — prints Text to stdout (no newline)"""
    if len(args) != 1:
        return
    text = args[0]
    if isinstance(text, str):
        print(text, end="")
        yield _proof(bindings)


@primitive("write-line")
def prim_write_line(args, bindings, engine):
    """write-line(Text) — prints Text to stdout followed by newline"""
    if len(args) != 1:
        return
    text = args[0]
    if isinstance(text, str):
        print(text)
        yield _proof(bindings)


@primitive("write-stderr")
def prim_write_stderr(args, bindings, engine):
    """write-stderr(Text) — prints Text to stderr (no newline)"""
    import sys as _sys
    if len(args) != 1:
        return
    text = args[0]
    if isinstance(text, str):
        _sys.stderr.write(text)
        yield _proof(bindings)


# ── Meta predicates ───────────────────────────────────────────────────────────

@primitive("assert-fact")
def prim_assert_fact(args, bindings, engine):
    """assert-fact(Subject, Predicate, Value) — asserts a fact into the graph.
    The fact is visible to subsequent queries in the same session."""
    if len(args) != 3:
        return
    subject, predicate, value = args
    # Convert AST-list duration representation to DurationLit
    if isinstance(value, list) and len(value) == 3 and value[0] == "duration":
        from logos.ast_nodes import DurationLit
        value = DurationLit(amount=float(value[1]), unit=value[2])
    if (isinstance(subject, str) and isinstance(predicate, str)
            and _is_ground(value)):
        from logos.semantic_graph import FactNode
        from logos.ast_nodes import DurationLit as _DL
        value_type = "Text" if isinstance(value, str) else \
                     "Integer" if isinstance(value, (int, float)) else \
                     "Duration" if isinstance(value, _DL) else "Entity"
        fact = FactNode.make(
            subject=subject,
            predicate=predicate,
            value=value,
            value_type=value_type,
            provenance_source="logos-assert",
        )
        engine.graph.assert_fact(fact)
        yield _proof(bindings)


@primitive("retract-fact")
def prim_retract_fact(args, bindings, engine):
    """retract-fact(Subject, Predicate) — retracts a fact from the graph"""
    if len(args) != 2:
        return
    subject, predicate = args
    if isinstance(subject, str) and isinstance(predicate, str):
        engine.graph.retract(subject, predicate)
        yield _proof(bindings)


@primitive("fact-exists")
def prim_fact_exists(args, bindings, engine):
    """fact-exists(Subject, Predicate) — succeeds if the fact is in the graph"""
    if len(args) != 2:
        return
    subject, predicate = args
    if isinstance(subject, str) and isinstance(predicate, str):
        result = engine.graph.query(subject, predicate)
        if result.found:
            yield _proof(bindings)


@primitive("ground")
def prim_ground(args, bindings, engine):
    """ground(X) — succeeds iff X is fully ground (not a variable)"""
    if len(args) != 1:
        return
    if _is_ground(args[0]):
        yield _proof(bindings)


@primitive("not-ground")
def prim_not_ground(args, bindings, engine):
    """not-ground(X) — succeeds iff X is an unbound variable"""
    if len(args) != 1:
        return
    if not _is_ground(args[0]):
        yield _proof(bindings)


@primitive("equal")
def prim_equal(args, bindings, engine):
    """equal(A, B) — unifies A and B (general unification)"""
    if len(args) != 2:
        return
    from logos.inference import unify_term
    new_b = unify_term(args[0], args[1], bindings)
    if new_b is not None:
        yield _proof(new_b)


@primitive("is-string")
def prim_is_string(args, bindings, engine):
    """is-string(V) — succeeds iff V is a Python string"""
    if len(args) != 1:
        return
    if isinstance(args[0], str):
        yield _proof(bindings)


@primitive("is-number")
def prim_is_number(args, bindings, engine):
    """is-number(V) — succeeds iff V is a number (int or float)"""
    if len(args) != 1:
        return
    if isinstance(args[0], (int, float)) and not isinstance(args[0], bool):
        yield _proof(bindings)


@primitive("is-list")
def prim_is_list(args, bindings, engine):
    """is-list(V) — succeeds iff V is a list"""
    if len(args) != 1:
        return
    if isinstance(args[0], list):
        yield _proof(bindings)


@primitive("not-equal")
def prim_not_equal(args, bindings, engine):
    """not-equal(A, B) — succeeds if A and B are different ground values"""
    if len(args) != 2:
        return
    a, b = args
    if _is_ground(a) and _is_ground(b) and a != b:
        yield _proof(bindings)


# ── Phase F: meta-primitives for evaluator.logos ──────────────────────────────


def _ast_to_value(ast_val: Any) -> Any:
    """Convert AST-list representation to a runtime Logos value."""
    from logos.ast_nodes import Path, DurationLit
    if not isinstance(ast_val, list):
        return ast_val
    if len(ast_val) == 0:
        return ast_val
    tag = ast_val[0]
    if tag == "id" and len(ast_val) == 2:
        return ast_val[1]  # plain identifier string
    if tag == "var" and len(ast_val) == 2:
        return Variable(name=ast_val[1])
    if tag == "path" and len(ast_val) == 3:
        return Path(parts=[ast_val[1], ast_val[2]])
    if tag == "path-var" and len(ast_val) == 3:
        return Path(parts=[ast_val[1], ast_val[2]])
    if tag == "duration" and len(ast_val) == 3:
        return DurationLit(amount=ast_val[1], unit=ast_val[2])
    return ast_val  # pass through strings, numbers, etc.


def _ast_to_condition(cond_ast: Any):
    """Convert condition AST-list to Python AST node."""
    from logos.ast_nodes import PredicateCall, NegatedPredicate, Comparison
    if not isinstance(cond_ast, list) or len(cond_ast) == 0:
        return None
    tag = cond_ast[0]
    if tag == "call" and len(cond_ast) == 3:
        name, args_ast = cond_ast[1], cond_ast[2]
        args = [_ast_to_value(a) for a in args_ast]
        return PredicateCall(name=name, args=args)
    if tag == "not-call" and len(cond_ast) == 3:
        name, args_ast = cond_ast[1], cond_ast[2]
        args = [_ast_to_value(a) for a in args_ast]
        return NegatedPredicate(predicate=PredicateCall(name=name, args=args))
    if tag == "cmp" and len(cond_ast) == 4:
        left = _ast_to_value(cond_ast[1])
        op = cond_ast[2]
        right = _ast_to_value(cond_ast[3])
        return Comparison(left=left, op=op, right=right)
    return None


@primitive("register-rule-ast")
def prim_register_rule_ast(args, bindings, engine):
    """register-rule-ast(Name, ArgsAst, CondsAst)
    Converts an AST-list rule representation to an InferenceRule and registers it."""
    if len(args) != 3:
        return
    name, args_ast, conds_ast = args
    if not isinstance(name, str):
        return
    from logos.ast_nodes import InferenceRule, PredicateCall
    head_args = [_ast_to_value(a) for a in (args_ast if isinstance(args_ast, list) else [])]
    head = PredicateCall(name=name, args=head_args)
    conditions = []
    for c in (conds_ast if isinstance(conds_ast, list) else []):
        cond = _ast_to_condition(c)
        if cond is not None:
            conditions.append(cond)
    rule = InferenceRule(head=head, conditions=conditions)
    engine.rules.append(rule)
    yield _proof(bindings)


@primitive("exec-bool-query-ast")
def prim_exec_bool_query_ast(args, bindings, engine):
    """exec-bool-query-ast(Name, ArgsAst) — run a bool query, print result."""
    if len(args) != 2:
        return
    name, args_ast = args
    if not isinstance(name, str):
        return
    from logos.ast_nodes import PredicateCall, BoolQuery
    call_args = [_ast_to_value(a) for a in (args_ast if isinstance(args_ast, list) else [])]
    goal = PredicateCall(name=name, args=call_args)
    results = list(engine.prove_all([goal]))
    found = any(r.success for r in results)
    print(f"{name}({', '.join(str(a) for a in call_args)}): {'true' if found else 'false'}")
    yield _proof(bindings)


@primitive("exec-find-query-ast")
def prim_exec_find_query_ast(args, bindings, engine):
    """exec-find-query-ast(VarsAst, CondsAst) — run a find query, print results."""
    if len(args) != 2:
        return
    vars_ast, conds_ast = args
    if not isinstance(vars_ast, list) or not isinstance(conds_ast, list):
        return
    from logos.ast_nodes import PredicateCall, Variable as Var
    var_names = [v for v in vars_ast if isinstance(v, str)]
    goals = [_ast_to_condition(c) for c in conds_ast]
    goals = [g for g in goals if g is not None]
    results = list(engine.prove_all(goals))
    found_any = False
    for r in results:
        if r.success:
            vals = {name: r.bindings.get(name) for name in var_names}
            if any(v is not None for v in vals.values()):
                found_any = True
                row = ", ".join(f"{k}={v}" for k, v in vals.items() if v is not None)
                print(f"  {row}")
    if not found_any:
        print("  (no results)")
    yield _proof(bindings)
