"""
Logos → C transpiler.

Transforms a Program AST into C source that can be compiled together with
logos_runtime.c to produce a native binary.

Backtracking model: continuation-passing style (CPS).  Each predicate
dispatcher tries all its clauses sequentially, undoing environment changes
between attempts.  Results are communicated through env->capture_found /
env->capture_conf rather than through the return value, so that all proof
paths are explored (OR-aggregation across multiple derivations).
"""

from __future__ import annotations
from typing import Any

from logos.ast_nodes import (
    Program, TypeDecl, SemanticBinding, InferenceRule,
    BoolQuery, FindQuery, PredicateCall, Comparison, NegatedPredicate,
    DurationLit, Variable, Path, SetLit, ListLit, ArithExpr,
    ImportStmt, Retraction, TransformDecl, ContextDecl,
)


class CompilationError(Exception):
    """Raised when a Logos program cannot be compiled to C."""


# Comparison operator → numeric code (matches logos_runtime.c logos_compare)
_OP_MAP: dict[str, int] = {">=": 0, "<=": 1, ">": 2, "<": 3, "=": 4, "!=": 5}

# Primitive predicates: name → (arity, C_function_name)
# These are implemented in logos_primitives.c and called inline (non-CPS).
PRIMITIVES: dict[str, tuple[int, str]] = {
    "equal":        (2, "logos_prim_equal"),
    "true":         (0, "logos_prim_true"),
    "list-cons":    (3, "logos_prim_list_cons"),
    "list-empty":   (1, "logos_prim_list_empty"),
    "list-head":    (2, "logos_prim_list_head"),
    "list-tail":    (2, "logos_prim_list_tail"),
    "list-length":  (2, "logos_prim_list_length"),
    "list-nth":     (3, "logos_prim_list_nth"),
    "list-append":  (3, "logos_prim_list_append"),
    "list-reverse": (2, "logos_prim_list_reverse"),
    "list-flatten": (2, "logos_prim_list_flatten"),
    "num-add":      (3, "logos_prim_num_add"),
    "num-sub":      (3, "logos_prim_num_sub"),
    "num-mul":      (3, "logos_prim_num_mul"),
    "num-div":      (3, "logos_prim_num_div"),
    "num-mod":      (3, "logos_prim_num_mod"),
    "num-abs":      (2, "logos_prim_num_abs"),
    "num-floor":    (2, "logos_prim_num_floor"),
    "num-ceil":     (2, "logos_prim_num_ceil"),
    "num-min":      (3, "logos_prim_num_min"),
    "num-max":      (3, "logos_prim_num_max"),
    "is-string":    (1, "logos_prim_is_string"),
    "is-number":    (1, "logos_prim_is_number"),
    "is-list":      (1, "logos_prim_is_list"),
    "ground":       (1, "logos_prim_ground"),
    # Dynamic fact assertion
    "assert-fact":  (3, "logos_prim_assert_fact"),
    # Meta-interpreter primitives
    "register-rule-ast":   (3, "logos_prim_register_rule_ast"),
    "exec-bool-query-ast": (2, "logos_prim_exec_bool_query_ast"),
    "exec-find-query-ast": (2, "logos_prim_exec_find_query_ast"),
    # String primitives
    "str-concat":      (3, "logos_prim_str_concat"),
    "str-length":      (2, "logos_prim_str_length"),
    "str-char-at":     (3, "logos_prim_str_char_at"),
    "str-starts-with": (2, "logos_prim_str_starts_with"),
    "str-ends-with":   (2, "logos_prim_str_ends_with"),
    "str-slice":       (4, "logos_prim_str_slice"),
    "str-to-number":   (2, "logos_prim_str_to_number"),
    "number-to-str":   (2, "logos_prim_number_to_str"),
    "str-split":       (3, "logos_prim_str_split"),
    "str-join":        (3, "logos_prim_str_join"),
    "str-unescape":    (2, "logos_prim_str_unescape"),
    "str-upper":       (2, "logos_prim_str_upper"),
    "str-lower":       (2, "logos_prim_str_lower"),
    "str-trim":        (2, "logos_prim_str_trim"),
    "str-contains":    (2, "logos_prim_str_contains"),
    # Character class predicates
    "char-alpha":      (1, "logos_prim_char_alpha"),
    "char-digit":      (1, "logos_prim_char_digit"),
    "char-whitespace": (1, "logos_prim_char_whitespace"),
    "char-alnum":      (1, "logos_prim_char_alnum"),
    "char-code":       (2, "logos_prim_char_code"),
    # Lexer primitives
    "lex-file":        (2, "logos_prim_lex_file"),
    "lex-source":      (2, "logos_prim_lex_source"),
    # I/O primitives
    "write-output":    (1, "logos_prim_write_output"),
    "write-line":      (1, "logos_prim_write_line"),
    "write-stderr":    (1, "logos_prim_write_stderr"),
    "read-file":       (2, "logos_prim_read_file"),
    # Command-line argument primitives
    "argv":            (2, "logos_prim_argv"),
    "argc":            (1, "logos_prim_argc"),
}


def _c_id(name: str) -> str:
    """Convert a Logos identifier to a valid C identifier fragment."""
    return name.replace("-", "_").replace(".", "_")


def _esc(s: str) -> str:
    """Escape a Python string for embedding in a C string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _csep(middle: str) -> str:
    """Return ', middle' when middle is non-empty, else empty string.

    Used to splice optional parameter/argument lists into C signatures and
    call sites without generating spurious double-commas for zero-arity rules.
    """
    return f", {middle}" if middle else ""


# ── Compiler ──────────────────────────────────────────────────────────────────

class Compiler:
    """Transforms a Program AST into a C source string."""

    def __init__(self, program: Program):
        self.program    = program
        self.facts:     list[SemanticBinding]                           = []
        self.rules:     list[InferenceRule]                             = []
        self.queries:   list[Any]                                       = []
        self.rules_by_pred: dict[str, list[tuple[int, InferenceRule]]] = {}
        self._tmp_ctr   = 0   # counter for unique temp-var names in setup

        for stmt in program.statements:
            if isinstance(stmt, SemanticBinding):
                self._check_binding(stmt)
                self.facts.append(stmt)
            elif isinstance(stmt, InferenceRule):
                pred = stmt.head.name
                if pred not in self.rules_by_pred:
                    self.rules_by_pred[pred] = []
                idx = len(self.rules_by_pred[pred])
                self.rules_by_pred[pred].append((idx, stmt))
                self.rules.append(stmt)
            elif isinstance(stmt, (BoolQuery, FindQuery)):
                self.queries.append(stmt)
            elif isinstance(stmt, TypeDecl):
                pass  # silently skipped
            elif isinstance(stmt, ImportStmt):
                pass  # resolved by compiler.resolve_imports() before we run
            # Retraction / TransformDecl / ContextDecl silently skipped

    # ── Validation ────────────────────────────────────────────────────────────

    def _check_binding(self, b: SemanticBinding) -> None:
        val = b.value
        if isinstance(val, SetLit):
            raise CompilationError(
                f"SetLit fact values are not supported in compiled mode (at {b.path})"
            )
        if isinstance(val, ArithExpr):
            raise CompilationError(
                f"ArithExpr fact values are not supported in compiled mode (at {b.path})"
            )

    # ── Top-level generation ──────────────────────────────────────────────────

    def generate(self) -> str:
        return "\n".join([
            self._emit_preamble(),
            self._emit_forward_decls(),
            self._emit_rule_functions(),
            self._emit_pred_dispatchers(),
            self._emit_setup(),
            self._emit_main(),
        ])

    # ── Preamble ──────────────────────────────────────────────────────────────

    def _emit_preamble(self) -> str:
        return (
            '/* Generated by Logos compiler — do not edit by hand */\n'
            '#include "logos_runtime.h"\n'
            '#include "logos_primitives.h"\n'
            '#include "logos_meta.h"\n'
            '#include "logos_lexer.h"\n'
            '#include <stdio.h>\n'
            '#include <string.h>\n'
            '#include <stdlib.h>\n'
            '\n'
        )

    # ── Forward declarations ──────────────────────────────────────────────────

    def _emit_forward_decls(self) -> str:
        lines = ["/* Forward declarations */"]
        for pred, clauses in self.rules_by_pred.items():
            first_rule = clauses[0][1]
            param_str  = self._pred_param_decl(first_rule)
            lines.append(
                f"static int rule_{_c_id(pred)}_0"
                f"(logos_env *env{_csep(param_str)}, logos_cont k);"
            )
            lines.append(
                f"int pred_{_c_id(pred)}"
                f"(logos_env *env{_csep(param_str)}, logos_cont k);"
            )
        lines.append("")
        return "\n".join(lines)

    def _pred_param_decl(self, rule: InferenceRule) -> str:
        parts = []
        seen: dict[str, int] = {}
        for pos, arg in enumerate(rule.head.args):
            base = self._head_arg_cname(arg, pos)
            if base in seen:
                seen[base] += 1
                cname = f"{base}_{seen[base]}"
            else:
                seen[base] = 0
                cname = base
            parts.append(f"logos_term var_{cname}")
        return ", ".join(parts)

    def _pred_param_pass(self, rule: InferenceRule) -> str:
        parts = []
        seen: dict[str, int] = {}
        for pos, arg in enumerate(rule.head.args):
            base = self._head_arg_cname(arg, pos)
            if base in seen:
                seen[base] += 1
                cname = f"{base}_{seen[base]}"
            else:
                seen[base] = 0
                cname = base
            parts.append(f"var_{cname}")
        return ", ".join(parts)

    def _head_arg_cname(self, arg: Any, pos: int = 0) -> str:
        if isinstance(arg, Variable):
            return _c_id(arg.name)
        elif isinstance(arg, Path):
            return _c_id(arg.root())
        else:
            # ListLit or constant: use position-based name
            return f"_harg{pos}"

    # ── Rule functions ────────────────────────────────────────────────────────

    def _emit_rule_functions(self) -> str:
        parts = []
        for pred, clauses in self.rules_by_pred.items():
            for idx, rule in clauses:
                emitter = RuleEmitter(rule, pred, idx, self)
                parts.append(emitter.emit())
        return "\n".join(parts)

    # ── Predicate dispatchers ─────────────────────────────────────────────────

    def _emit_pred_dispatchers(self) -> str:
        parts = []
        for pred, clauses in self.rules_by_pred.items():
            cname      = _c_id(pred)
            first_rule = clauses[0][1]
            param_decl = self._pred_param_decl(first_rule)
            param_pass = self._pred_param_pass(first_rule)
            lines = [
                f"int pred_{cname}(logos_env *env{_csep(param_decl)}, logos_cont k) {{",
            ]
            for idx, _rule in clauses:
                lines.append(f"    {{ logos_mark_t _m = logos_mark(env);")
                lines.append(
                    f"    if (rule_{cname}_{idx}(env{_csep(param_pass)}, k))"
                    f" {{ logos_undo(env, _m); return 1; }}"
                )
                lines.append(f"    logos_undo(env, _m); }}")
            lines.append(f"    return 0;")
            lines.append(f"}}")
            lines.append("")
            parts.append("\n".join(lines))
        return "\n".join(parts)

    # ── logos_setup ───────────────────────────────────────────────────────────

    def _emit_setup(self) -> str:
        lines = ["void logos_setup(logos_graph *g) {"]
        for b in self.facts:
            subj, pred = self._decompose_path(b.path)
            conf       = self._get_confidence(b)
            setup: list[str] = []
            val_expr   = self._emit_value_stmts(b.value, setup, indent="    ")
            lines.extend(setup)
            lines.append(
                f'    logos_graph_assert(g, "{_esc(subj)}", '
                f'"{_esc(pred)}", {val_expr}, {conf});'
            )
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _decompose_path(self, path: Path) -> tuple[str, str]:
        if len(path.parts) == 1:
            return (path.parts[0], "value")
        return (path.parts[0], path.parts[1])

    # ── Value emission (possibly multi-statement for lists) ───────────────────

    def _tmp_fresh(self, prefix: str = "_sv") -> str:
        self._tmp_ctr += 1
        return f"{prefix}_{self._tmp_ctr}"

    def _emit_value_stmts(self, value: Any, setup: list[str],
                          indent: str = "    ") -> str:
        """Emit value construction statements into *setup*, return C expression.

        For scalar values (string, int, duration …) setup remains empty and
        the returned string is an inline C expression.  For ListLit, one or
        more `logos_term _sv_N = …;` statements are appended to setup and the
        returned string is the last temp-variable name.
        """
        if isinstance(value, ListLit):
            return self._emit_list_stmts(value, setup, indent)
        else:
            return self._emit_value(value)

    def _emit_list_stmts(self, lst: ListLit, setup: list[str],
                         indent: str = "    ") -> str:
        """Emit a list construction as sequential statements; return final var."""
        if not lst.elements:
            return "logos_nil()"
        cur = "logos_nil()"
        for elt in reversed(lst.elements):
            elt_expr = self._emit_value_stmts(elt, setup, indent)
            tmp = self._tmp_fresh("_sv")
            setup.append(f"{indent}logos_term {tmp} = logos_list_cons({elt_expr}, {cur});")
            cur = tmp
        return cur

    def _emit_value(self, value: Any) -> str:
        """Return an inline C expression for a scalar value."""
        if isinstance(value, DurationLit):
            return f"logos_duration({value.to_seconds()})"
        elif isinstance(value, bool):
            return f"logos_int({1 if value else 0})"
        elif isinstance(value, int):
            return f"logos_int({value})"
        elif isinstance(value, float):
            return f"logos_float({value})"
        elif isinstance(value, str):
            return f'logos_string("{_esc(value)}")'
        elif isinstance(value, ListLit):
            # Caller should use _emit_value_stmts; this path is a fallback for
            # contexts where setup statements aren't available (e.g. query args)
            raise CompilationError(
                "ListLit in expression context requires _emit_value_stmts"
            )
        elif isinstance(value, SetLit):
            raise CompilationError("SetLit not supported in compiled mode")
        elif isinstance(value, ArithExpr):
            raise CompilationError("ArithExpr not supported in compiled mode")
        else:
            return f'logos_string("{_esc(str(value))}")'

    def _get_confidence(self, b: SemanticBinding) -> str:
        ann = b.annotations
        if ann and ann.confidence:
            raw = ann.confidence.raw
            if raw == "absolute":
                return "1.0"
            elif isinstance(raw, (int, float)):
                return str(float(raw))
            elif isinstance(raw, tuple):
                return str(float((raw[0] + raw[1]) / 2.0))
        return "1.0"

    # ── main() ────────────────────────────────────────────────────────────────

    def _emit_main(self) -> str:
        lines = [
            "int main(int argc, char **argv) {",
            "    logos_argc = argc; logos_argv = argv;",
            "    logos_graph graph;",
            "    logos_graph_init(&graph);",
            "    logos_env   env   = {0};",
            "    logos_env_init(&env);",
            "    env.graph = &graph;",
            "    logos_setup(&graph);",
            "",
        ]
        for q in self.queries:
            if isinstance(q, BoolQuery):
                lines.extend(self._emit_bool_query(q))
            elif isinstance(q, FindQuery):
                lines.extend(self._emit_find_query(q))
        lines.append("    return 0;")
        lines.append("}")
        return "\n".join(lines)

    # ── BoolQuery emission ────────────────────────────────────────────────────

    def _emit_bool_query(self, q: BoolQuery) -> list[str]:
        pred  = q.predicate.name
        cname = _c_id(pred)
        args  = q.predicate.args
        text  = f"{pred}({', '.join(self._query_text_arg(a) for a in args)})"

        setup: list[str] = []
        arg_exprs = ", ".join(
            self._emit_value_stmts(a, setup, indent="        ")
            if isinstance(a, ListLit)
            else self._query_term(a)
            for a in args
        )

        lines = ["    {"]
        lines.extend(setup)

        if pred in PRIMITIVES:
            # Primitive predicates: call directly, no CPS overhead
            _, cfunc = PRIMITIVES[pred]
            sep = ", " if arg_exprs else ""
            lines += [
                f"        int    _found = {cfunc}(&env{sep}{arg_exprs});",
                "        double _conf  = _found ? 1.0 : 0.0;",
                f'        logos_print_bool_result("{_esc(text)}", _found, _conf);',
            ]
        else:
            lines += [
                "        int    _found = 0;",
                "        double _conf  = 0.0;",
                "        env.capture_found = &_found;",
                "        env.capture_conf  = &_conf;",
                "        env.confidence    = 1.0;",
                f"        pred_{cname}(&env{_csep(arg_exprs)}, k_bool_capture);",
                f'        logos_print_bool_result("{_esc(text)}", _found, _conf);',
            ]

        lines.append("    }")
        return lines

    def _query_term(self, arg: Any) -> str:
        if isinstance(arg, Path) and len(arg.parts) == 1:
            return f'logos_string("{_esc(arg.parts[0])}")'
        elif isinstance(arg, str):
            return f'logos_string("{_esc(arg)}")'
        elif isinstance(arg, bool):
            return f"logos_int({1 if arg else 0})"
        elif isinstance(arg, int):
            return f"logos_int({arg})"
        elif isinstance(arg, float):
            return f"logos_float({arg})"
        elif isinstance(arg, DurationLit):
            return f"logos_duration({arg.to_seconds()})"
        else:
            return f'logos_string("{_esc(str(arg))}")'

    def _query_text_arg(self, arg: Any) -> str:
        if isinstance(arg, Path):
            return str(arg)
        elif isinstance(arg, Variable):
            return arg.name
        elif isinstance(arg, ListLit):
            inner = ", ".join(self._query_text_arg(e) for e in arg.elements)
            return f"[{inner}]"
        else:
            return str(arg)

    # ── FindQuery emission ────────────────────────────────────────────────────

    def _emit_find_query(self, q: FindQuery) -> list[str]:
        var_names  = [v.name for v in q.variables]
        pred_conds = [c for c in q.conditions if isinstance(c, PredicateCall)]
        if not pred_conds:
            return [
                "    {",
                "        /* find query: no predicate conditions, skipping */",
                "    }",
            ]

        pc    = pred_conds[0]
        cname = _c_id(pc.name)
        nv    = len(var_names)

        def arg_expr(a: Any) -> str:
            if isinstance(a, Variable) and a.name in var_names:
                return "logos_string(_s)"
            return self._query_term(a)

        arg_exprs  = ", ".join(arg_expr(a) for a in pc.args)
        vnames_lit = "{" + ", ".join(f'"{n}"' for n in var_names) + "}"

        def val_expr(v: Variable) -> str:
            for a in pc.args:
                if isinstance(a, Variable) and a.name == v.name:
                    return "logos_string(_s)"
            return f'logos_string("{v.name}")'

        vals_lit = "{" + ", ".join(val_expr(v) for v in q.variables) + "}"

        return [
            "    {",
            f"        /* find {', '.join(var_names)} where {pc.name}(...) */",
            "        const char *_seen[LOGOS_MAX_FACTS];",
            "        int _nseen = 0, _i, _j;",
            "        memset(_seen, 0, sizeof(_seen));",
            "        for (_i = 0; _i < graph.count; _i++) {",
            "            const char *_s = graph.facts[_i].subject;",
            "            int _dup = 0;",
            "            for (_j = 0; _j < _nseen; _j++)",
            "                if (_seen[_j] == _s) { _dup = 1; break; }",
            "            if (_dup) continue;",
            "            _seen[_nseen++] = _s;",
            "            {",
            "                int    _found = 0;",
            "                double _conf  = 0.0;",
            "                env.capture_found = &_found;",
            "                env.capture_conf  = &_conf;",
            "                env.confidence    = 1.0;",
            f"                pred_{cname}(&env{_csep(arg_exprs)}, k_bool_capture);",
            "                if (_found) {",
            f"                    const char *_vnames[{nv}] = {vnames_lit};",
            f"                    logos_term   _vals[{nv}]   = {vals_lit};",
            f"                    logos_print_find_row(_vnames, _vals, {nv}, _conf);",
            "                }",
            "            }",
            "        }",
            "    }",
        ]


# ── RuleEmitter ───────────────────────────────────────────────────────────────

class RuleEmitter:
    """Emits one C function for a single InferenceRule clause."""

    def __init__(self, rule: InferenceRule, pred_name: str, idx: int,
                 compiler: Compiler):
        self.rule      = rule
        self.pred_name = pred_name
        self.idx       = idx
        self.compiler  = compiler
        self._ctr      = 0

        # Build per-position parameter names (deduplicating within this rule's
        # signature) and record any duplicate positions for head-unification.
        self._var_map: dict[str, str] = {}
        self._head_param_names: list[str] = []  # cname per head arg position
        self._head_dup_pairs:   list[tuple[str, str]] = []  # (first, dup)
        # ListLit head pattern args: (pos, param_cname, ListLit node)
        self._head_pattern_args: list[tuple[int, str, ListLit]] = []
        # Variables extracted from head ListLit patterns (need logos_alloc_var)
        self._head_list_vars: list[str] = []

        # Pass 1: build _head_param_names and populate _var_map for plain vars.
        seen: dict[str, str] = {}  # base_cname → first param cname
        for pos, arg in enumerate(rule.head.args):
            if isinstance(arg, Variable):
                base = _c_id(arg.name)
                is_plain_var = True
            elif isinstance(arg, Path) and len(arg.parts) == 1:
                name0 = arg.parts[0]
                if name0 and name0[0].isupper():
                    # Uppercase single-part path = variable reference
                    base = _c_id(name0)
                    is_plain_var = True
                else:
                    # Lowercase single-part path = constant; needs unification
                    base = f"_harg{pos}"
                    is_plain_var = False
            else:
                # ListLit or constant: position-based name
                base = f"_harg{pos}"
                is_plain_var = False

            if base in seen:
                cnt = sum(1 for n in self._head_param_names if n.startswith(base))
                cname = f"{base}_{cnt}"
                self._head_dup_pairs.append((seen[base], cname))
            else:
                cname = base
                seen[base] = cname
                if is_plain_var:
                    self._var_map[base] = f"var_{base}"

            self._head_param_names.append(cname)

        # Pass 2: for all non-plain-variable head args (ListLit or constants),
        # record them for pattern unification at rule entry.  All plain-var
        # params are now in _var_map, so shared variables (appearing in both a
        # ListLit and another head arg position) are correctly excluded from
        # _head_list_vars.
        for pos, arg in enumerate(rule.head.args):
            is_plain_var = (
                isinstance(arg, Variable)
                or (isinstance(arg, Path) and len(arg.parts) == 1
                    and arg.parts[0] and arg.parts[0][0].isupper())
            )
            if not is_plain_var:
                cname = self._head_param_names[pos]
                self._head_pattern_args.append((pos, cname, arg))
                if isinstance(arg, ListLit):
                    for v in self._extract_list_vars(arg):
                        if v not in self._var_map:
                            self._head_list_vars.append(v)
                            self._var_map[v] = f"var_{_c_id(v)}"

        # Body-local variables: Variables in conditions not already in head
        self._body_vars: list[str] = self._collect_body_vars()

    def _fresh(self) -> int:
        self._ctr += 1
        return self._ctr

    def _collect_body_vars(self) -> list[str]:
        """Return sorted list of variable names used in rule body but not head."""
        def scan(node: Any) -> set[str]:
            if isinstance(node, Variable):
                return {node.name}
            elif isinstance(node, Path):
                # Single-part uppercase paths inside list literals are variables.
                if len(node.parts) == 1 and node.parts[0] and node.parts[0][0].isupper():
                    return {node.parts[0]}
                return set()
            elif isinstance(node, PredicateCall):
                result: set[str] = set()
                for a in node.args:
                    result |= scan(a)
                return result
            elif isinstance(node, Comparison):
                return scan(node.left) | scan(node.right)
            elif isinstance(node, NegatedPredicate):
                return scan(node.predicate)
            elif isinstance(node, ListLit):
                result2: set[str] = set()
                for e in node.elements:
                    result2 |= scan(e)
                return result2
            return set()

        body_vars: set[str] = set()
        for cond in self.rule.conditions:
            body_vars |= scan(cond)
        return sorted(v for v in body_vars if v not in self._var_map)

    def _extract_list_vars(self, listlit: ListLit) -> list[str]:
        """Extract variable names embedded in a ListLit head pattern.

        Variables appear as single-part Path objects whose first character
        is uppercase (Logos convention).  Recurses into nested ListLits.
        """
        result: list[str] = []
        for elt in listlit.elements:
            if isinstance(elt, Path) and len(elt.parts) == 1:
                name = elt.parts[0]
                if name and name[0].isupper():
                    result.append(name)
            elif isinstance(elt, Variable):
                result.append(elt.name)
            elif isinstance(elt, ListLit):
                result.extend(self._extract_list_vars(elt))
        return result

    # ── Variable map initialisation ───────────────────────────────────────────

    def _init_var_map(self) -> None:
        """Populate _var_map for body-local variables (called before emit)."""
        for bv in self._body_vars:
            self._var_map[bv] = f"var_{_c_id(bv)}"

    # ── All variable names (head + body) ─────────────────────────────────────

    def _all_var_names(self) -> list[str]:
        """Sorted list of all variable names for this rule."""
        return sorted(self._var_map.keys())

    # ── Context struct name ───────────────────────────────────────────────────

    def _ctx_struct(self) -> str:
        return f"_ctx_{_c_id(self.pred_name)}_{self.idx}"

    # ── Find user-defined predicate call positions ────────────────────────────

    def _split_positions(self) -> list[int]:
        return [
            i for i, c in enumerate(self.rule.conditions)
            if isinstance(c, PredicateCall) and c.name not in PRIMITIVES
        ]

    # ── Function skeleton ─────────────────────────────────────────────────────

    def emit(self) -> str:
        self._init_var_map()
        splits = self._split_positions()
        if splits:
            return self._emit_cps_rule(splits)
        return self._emit_simple_rule()

    # ── Head pattern unification helper ──────────────────────────────────────

    def _emit_head_pattern_unifications(self, lines: list[str]) -> None:
        """Allocate head-extracted list vars and unify all head pattern args.

        Handles ListLit patterns (which may contain variables) and scalar
        constants (strings, numbers, etc.) at non-variable head positions.
        """
        for v in self._head_list_vars:
            lines.append(f"    logos_term var_{_c_id(v)} = logos_alloc_var(env);")
        for _pos, param_cn, pattern in self._head_pattern_args:
            setup: list[str] = []
            pattern_expr = self._emit_term(pattern, setup)
            lines.extend(setup)
            lines.append(
                f"    if (!logos_unify(env, var_{param_cn}, {pattern_expr})) return 0;"
            )

    # ── Simple rule (no user-defined predicate calls) ─────────────────────────

    def _emit_simple_rule(self) -> str:
        cname     = _c_id(self.pred_name)
        param_str = ", ".join(
            f"logos_term var_{cn}" for cn in self._head_param_names
        )
        lines = [
            f"static int rule_{cname}_{self.idx}"
            f"(logos_env *env{_csep(param_str)}, logos_cont k) {{",
        ]
        for bv in self._body_vars:
            lines.append(f"    logos_term var_{_c_id(bv)} = logos_alloc_var(env);")
        for first_cn, dup_cn in self._head_dup_pairs:
            lines.append(
                f"    if (!logos_unify(env, var_{first_cn}, var_{dup_cn})) return 0;"
            )
        self._emit_head_pattern_unifications(lines)
        for i, cond in enumerate(self.rule.conditions):
            lines.extend(self._emit_cond(cond, i))
        lines.append("    env->confidence = logos_degrade(env->confidence);")
        lines.append("    return k(env);")
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # ── CPS rule (has user-defined predicate call conditions) ─────────────────

    def _emit_cps_rule(self, splits: list[int]) -> str:
        """Emit context typedef + continuation functions + rule function."""
        ctx    = self._ctx_struct()
        avars  = self._all_var_names()
        cname  = _c_id(self.pred_name)
        parts: list[str] = []

        # 1. Context typedef (shared by all split points in this rule)
        parts.append(self._emit_ctx_typedef(ctx, avars))

        # 2. Continuation functions, bottom-up (last split first)
        for si in reversed(range(len(splits))):
            parts.append(self._emit_cont_func(
                ctx, avars, cname, splits, si
            ))

        # 3. Rule function
        parts.append(self._emit_rule_func_cps(ctx, avars, cname, splits))
        return "\n".join(parts)

    def _emit_ctx_typedef(self, struct_name: str,
                          avars: list[str]) -> str:
        lines = [f"typedef struct {{"]
        for v in avars:
            lines.append(f"    logos_term var_{_c_id(v)};")
        lines.append("    logos_cont k;")
        lines.append("    void *prev_ctx;")
        lines.append(f"}} {struct_name}_t;")
        lines.append("")
        return "\n".join(lines)

    def _emit_cont_func(self, ctx: str, avars: list[str],
                        pred_cname: str,
                        splits: list[int], si: int) -> str:
        """Emit _cont_PRED_IDX_SPLITPOS that handles conditions after splits[si]."""
        sp_pos    = splits[si]
        func_name = f"_cont_{pred_cname}_{self.idx}_{sp_pos}"
        conds     = self.rule.conditions

        lines = [f"static int {func_name}(logos_env *env) {{"]
        lines.append(f"    {ctx}_t *_ctx = ({ctx}_t *)env->cont_ctx;")
        for v in avars:
            cv = _c_id(v)
            lines.append(f"    logos_term var_{cv} = _ctx->var_{cv};")
        lines.append("    logos_cont k = _ctx->k;")
        lines.append("    void *_prev_ctx = _ctx->prev_ctx; env->cont_ctx = _prev_ctx; /* caller frees */")

        # Determine the range of conditions this function handles
        # and whether there is a next split point within that range
        next_splits = splits[si + 1:]  # split positions after this one

        if not next_splits:
            # No more splits: emit remaining conditions inline + degrade + k
            for i in range(sp_pos + 1, len(conds)):
                lines.extend(self._emit_cond(conds[i], i))
            lines.append("    env->confidence = logos_degrade(env->confidence);")
            lines.append("    return k(env);")
        else:
            next_sp = next_splits[0]
            # Inline conditions between this split and the next
            for i in range(sp_pos + 1, next_sp):
                lines.extend(self._emit_cond(conds[i], i))
            # CPS split at next_sp
            next_cont = f"_cont_{pred_cname}_{self.idx}_{next_sp}"
            lines.extend(
                self._emit_cps_split(ctx, avars, conds[next_sp], next_sp,
                                     next_cont)
            )

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _emit_rule_func_cps(self, ctx: str, avars: list[str],
                            pred_cname: str,
                            splits: list[int]) -> str:
        param_str = ", ".join(
            f"logos_term var_{cn}" for cn in self._head_param_names
        )
        conds  = self.rule.conditions
        first_sp = splits[0]

        lines = [
            f"static int rule_{pred_cname}_{self.idx}"
            f"(logos_env *env{_csep(param_str)}, logos_cont k) {{",
        ]
        for bv in self._body_vars:
            lines.append(f"    logos_term var_{_c_id(bv)} = logos_alloc_var(env);")
        for first_cn, dup_cn in self._head_dup_pairs:
            lines.append(
                f"    if (!logos_unify(env, var_{first_cn}, var_{dup_cn})) return 0;"
            )
        self._emit_head_pattern_unifications(lines)
        # Inline conditions before first split
        for i in range(first_sp):
            lines.extend(self._emit_cond(conds[i], i))
        # CPS split at first split
        first_cont = f"_cont_{pred_cname}_{self.idx}_{first_sp}"
        lines.extend(
            self._emit_cps_split(ctx, avars, conds[first_sp], first_sp,
                                 first_cont)
        )
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    def _emit_cps_split(self, ctx: str, avars: list[str],
                        cond: PredicateCall, idx: int,
                        cont_func: str) -> list[str]:
        """Emit the CPS split for a user-defined predicate call."""
        pred_cname = _c_id(cond.name)
        setup: list[str] = []
        arg_exprs = ", ".join(self._emit_term(a, setup) for a in cond.args)

        all_ctx_parts = [f"var_{_c_id(v)}" for v in avars] + ["k", "env->cont_ctx"]
        ctx_inits = ", ".join(all_ctx_parts)
        lines = [f"    /* CPS: {cond.name}({', '.join(str(a) for a in cond.args)}) */"]
        lines.extend(setup)
        lines += [
            f"    {{",
            f"        {ctx}_t *_ctx_{idx} = memcpy(malloc(sizeof({ctx}_t)), &({ctx}_t){{ {ctx_inits} }}, sizeof({ctx}_t));",
            f"        env->cont_ctx = _ctx_{idx};",
            f"        int _r_{idx} = pred_{pred_cname}(env{_csep(arg_exprs)}, {cont_func});",
            f"        env->cont_ctx = _ctx_{idx}->prev_ctx;",
            f"        free(_ctx_{idx});",
            f"        return _r_{idx};",
            f"    }}",
        ]
        return lines

    # ── Condition dispatch ────────────────────────────────────────────────────

    def _emit_cond(self, cond: Any, idx: int) -> list[str]:
        if isinstance(cond, Comparison):
            return self._emit_comparison(cond, idx)
        elif isinstance(cond, PredicateCall):
            if cond.name in PRIMITIVES:
                return self._emit_primitive_call(cond, idx)
            return self._emit_pred_call_cond(cond, idx)
        elif isinstance(cond, NegatedPredicate):
            if cond.predicate.name in PRIMITIVES:
                return self._emit_negated_primitive(cond, idx)
            return self._emit_negation(cond, idx)
        else:
            raise CompilationError(
                f"Unsupported condition type in compiled mode: {type(cond).__name__}"
            )

    # ── Primitive call condition (inline, non-CPS) ────────────────────────────

    def _emit_primitive_call(self, cond: PredicateCall, idx: int) -> list[str]:
        _, cfunc = PRIMITIVES[cond.name]
        setup: list[str] = []
        arg_exprs = ", ".join(self._emit_term(a, setup) for a in cond.args)
        sep = ", " if arg_exprs else ""
        lines = [f"    /* primitive: {cond.name}(...) */"]
        lines.extend(setup)
        lines.append(f"    if (!{cfunc}(env{sep}{arg_exprs})) return 0;")
        return lines

    def _emit_negated_primitive(self, cond: NegatedPredicate,
                                idx: int) -> list[str]:
        pc = cond.predicate
        _, cfunc = PRIMITIVES[pc.name]
        setup: list[str] = []
        arg_exprs = ", ".join(self._emit_term(a, setup) for a in pc.args)
        sep = ", " if arg_exprs else ""
        # NAF for a primitive: save bindings, test, undo, fail if succeeded
        lines = [f"    /* not {pc.name}(...) — primitive NAF */"]
        lines.extend(setup)
        lines += [
            f"    {{",
            f"        logos_mark_t _pnaf_{idx} = logos_mark(env);",
            f"        int _pnaf_ok_{idx} = {cfunc}(env{sep}{arg_exprs});",
            f"        logos_undo(env, _pnaf_{idx});",
            f"        if (_pnaf_ok_{idx}) return 0;",
            f"    }}",
        ]
        return lines

    # ── Comparison condition ──────────────────────────────────────────────────

    def _emit_comparison(self, cond: Comparison, idx: int) -> list[str]:
        left   = cond.left
        op     = cond.op
        right  = cond.right
        op_num = _OP_MAP.get(op, 4)

        # Graph-path comparison: subject.predicate OP value
        if isinstance(left, Path) and len(left.parts) == 2:
            subj_part = left.parts[0]
            pred_part = left.parts[1]
            # Subject: quoted string literal vs variable
            if subj_part.startswith('"') and subj_part.endswith('"'):
                c_subj_expr = f'"{_esc(subj_part[1:-1])}"'
            else:
                c_subj_var = self._resolve_var(subj_part)
                c_subj_expr = f"logos_walk(env, {c_subj_var}).s"
            # Predicate: strip quotes if present
            pred_c = pred_part[1:-1] if (pred_part.startswith('"') and pred_part.endswith('"')) else pred_part

            setup: list[str] = []
            rhs_expr = self._emit_term(right, setup)

            lines = [f"    /* {left} {op} {right} */", "    {"]
            lines.extend(setup)
            lines += [
                f"        logos_term _val_{idx}; double _conf_{idx};",
                f"        if (!logos_graph_lookup(env->graph,",
                f'                {c_subj_expr}, "{_esc(pred_c)}",',
                f"                &_val_{idx}, &_conf_{idx})) return 0;",
                f"        logos_term _rhs_{idx} = {rhs_expr};",
                f"        if (!logos_compare(_val_{idx}, {op_num}, _rhs_{idx})) return 0;",
                f"        env->confidence = logos_conjoin(env->confidence, _conf_{idx});",
                "    }",
            ]
            return lines

        # Direct comparison: variable/literal OP variable/literal
        # Both sides are resolved as terms and walked before comparing.
        setup2: list[str] = []
        lhs_expr = self._emit_term(left,  setup2)
        rhs_expr = self._emit_term(right, setup2)
        lines2 = [f"    /* {left} {op} {right} */"]
        lines2.extend(setup2)
        lines2.append(
            f"    if (!logos_compare("
            f"logos_walk(env, {lhs_expr}), {op_num}, "
            f"logos_walk(env, {rhs_expr}))) return 0;"
        )
        return lines2

    # ── Predicate call condition ──────────────────────────────────────────────

    def _emit_pred_call_cond(self, cond: PredicateCall, idx: int) -> list[str]:
        cname = _c_id(cond.name)
        setup: list[str] = []
        arg_exprs = ", ".join(self._emit_term(a, setup) for a in cond.args)

        lines = [
            f"    /* condition: {cond.name}(...) */",
            f"    {{",
        ]
        lines.extend(setup)
        lines += [
            f"        int    _pc_found_{idx} = 0;",
            f"        double _pc_conf_{idx}  = 0.0;",
            f"        void *_pf_{idx} = env->capture_found;",
            f"        void *_pc_{idx} = env->capture_conf;",
            f"        logos_mark_t _pm_{idx} = logos_mark(env);",
            f"        env->capture_found = &_pc_found_{idx};",
            f"        env->capture_conf  = &_pc_conf_{idx};",
            f"        pred_{cname}(env{_csep(arg_exprs)}, k_bool_capture);",
            f"        logos_undo(env, _pm_{idx});",
            f"        env->capture_found = _pf_{idx};",
            f"        env->capture_conf  = _pc_{idx};",
            f"        if (!_pc_found_{idx}) return 0;",
            f"        env->confidence = logos_conjoin(env->confidence, _pc_conf_{idx});",
            f"    }}",
        ]
        return lines

    # ── Negation-as-failure ───────────────────────────────────────────────────

    def _emit_negation(self, cond: NegatedPredicate, idx: int) -> list[str]:
        pc    = cond.predicate
        cname = _c_id(pc.name)
        setup: list[str] = []
        arg_exprs = ", ".join(self._emit_term(a, setup) for a in pc.args)

        lines = [
            f"    /* not {pc.name}(...) — negation-as-failure */",
            f"    {{",
        ]
        lines.extend(setup)
        lines += [
            f"        int    _naf_found_{idx} = 0;",
            f"        double _naf_conf_{idx}  = 0.0;",
            f"        void *_pf_{idx} = env->capture_found;",
            f"        void *_pc_{idx} = env->capture_conf;",
            f"        logos_mark_t _nm_{idx} = logos_mark(env);",
            f"        env->capture_found = &_naf_found_{idx};",
            f"        env->capture_conf  = &_naf_conf_{idx};",
            f"        pred_{cname}(env{_csep(arg_exprs)}, k_bool_capture);",
            f"        logos_undo(env, _nm_{idx});",
            f"        env->capture_found = _pf_{idx};",
            f"        env->capture_conf  = _pc_{idx};",
            f"        if (_naf_found_{idx}) return 0;  /* NAF: fail if proved */",
            f"    }}",
        ]
        return lines

    # ── Term emission (with optional setup for lists) ─────────────────────────

    def _emit_term(self, term: Any, setup: list[str]) -> str:
        """Return a C expression for *term*, emitting any needed construction
        statements into *setup* first.  Always use this method (not
        _resolve_term) when the term might be a ListLit."""
        if isinstance(term, ListLit):
            if not term.elements:
                return "logos_nil()"
            # Build from back to front; each step emits one statement.
            cur = "logos_nil()"
            for elt in reversed(term.elements):
                elt_expr = self._emit_term(elt, setup)
                n = self._fresh()
                tmp = f"_ls_{n}"
                setup.append(
                    f"        logos_term {tmp} = logos_list_cons({elt_expr}, {cur});"
                )
                cur = tmp
            return cur
        else:
            return self._resolve_term(term)

    # ── Term resolution (scalars only) ────────────────────────────────────────

    def _resolve_var(self, name: str) -> str:
        if name in self._var_map:
            return self._var_map[name]
        return f"var_{_c_id(name)}"

    def _resolve_term(self, term: Any) -> str:
        """C expression for a scalar term (no setup statements needed)."""
        if isinstance(term, Variable):
            return self._resolve_var(term.name)
        elif isinstance(term, Path):
            if len(term.parts) == 1:
                name = term.parts[0]
                if name[0].isupper() and name in self._var_map:
                    return self._var_map[name]
                return f'logos_string("{_esc(name)}")'
            else:
                raise CompilationError(
                    f"Multi-part path {term} used as a term — "
                    f"not supported in compiled mode"
                )
        elif isinstance(term, bool):
            return f"logos_int({1 if term else 0})"
        elif isinstance(term, int):
            return f"logos_int({term})"
        elif isinstance(term, float):
            return f"logos_float({term})"
        elif isinstance(term, str):
            return f'logos_string("{_esc(term)}")'
        elif isinstance(term, DurationLit):
            return f"logos_duration({term.to_seconds()})"
        elif isinstance(term, ListLit):
            raise CompilationError(
                "ListLit encountered in _resolve_term — use _emit_term instead"
            )
        else:
            raise CompilationError(
                f"Unsupported term type in compiled mode: "
                f"{type(term).__name__}: {term!r}"
            )
