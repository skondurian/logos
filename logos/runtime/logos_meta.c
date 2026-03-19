/*
 * logos_meta.c — Runtime meta-interpreter for the Logos self-hosted evaluator.
 *
 * Three primitives: register-rule-ast, exec-bool-query-ast, exec-find-query-ast.
 *
 * Variable semantics: within a clause attempt a logos_meta_env_t maps Logos
 * variable names (strings) to logos VAR terms allocated in the live env.
 * logos_mark() / logos_undo() now also save/restore env->bindings.num_vars,
 * so variable slots are reclaimed on backtracking.
 *
 * Backtracking:
 *   - exec-bool-query-ast: tries ALL matching clauses, accumulates confidence.
 *   - _meta_try_dyn_pred (used by _meta_call inside conditions): first-match,
 *     leaves bindings intact so later conditions in the same body can use them.
 */

#include "logos_meta.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* ── Dynamic rule table ─────────────────────────────────────────────────────── */

#define LOGOS_MAX_DYN_RULES  4096
#define LOGOS_META_MAX_VARS   128
#define LOGOS_META_MAX_ARGS    64

typedef struct {
    const char *name;        /* interned predicate name          */
    logos_term  head_args;   /* cons-list of head arg AST nodes  */
    logos_term  conditions;  /* cons-list of condition AST nodes */
} logos_dyn_rule_t;

static logos_dyn_rule_t _dyn_rules[LOGOS_MAX_DYN_RULES];
static int              _n_dyn_rules = 0;

/* ── Meta-variable environment ──────────────────────────────────────────────── */

typedef struct {
    logos_env  *env;
    const char *names[LOGOS_META_MAX_VARS];
    logos_term  vars [LOGOS_META_MAX_VARS];
    int         count;
} logos_meta_env_t;

static logos_term _meta_get_var(logos_meta_env_t *me, const char *name) {
    int i;
    name = logos_intern(name);
    for (i = 0; i < me->count; i++)
        if (me->names[i] == name) return me->vars[i];
    if (me->count >= LOGOS_META_MAX_VARS) {
        fprintf(stderr, "logos_meta: variable limit exceeded\n");
        return logos_nil();
    }
    {
        logos_term v     = logos_alloc_var(me->env);
        me->names[me->count] = name;
        me->vars [me->count] = v;
        me->count++;
        return v;
    }
}

/* ── Interned tag strings (initialised lazily) ─────────────────────────────── */

static const char *_TAG_VAR      = NULL;
static const char *_TAG_ID       = NULL;
static const char *_TAG_PATH     = NULL;
static const char *_TAG_PATHVAR  = NULL;
static const char *_TAG_CALL     = NULL;
static const char *_TAG_NOTCALL  = NULL;
static const char *_TAG_CMP      = NULL;

static void _ensure_tags(void) {
    if (!_TAG_VAR) {
        _TAG_VAR     = logos_intern("var");
        _TAG_ID      = logos_intern("id");
        _TAG_PATH    = logos_intern("path");
        _TAG_PATHVAR = logos_intern("path-var");
        _TAG_CALL    = logos_intern("call");
        _TAG_NOTCALL = logos_intern("not-call");
        _TAG_CMP     = logos_intern("cmp");
    }
}

/* ── Value resolution: AST node → runtime logos_term ────────────────────────── */

static logos_term _meta_resolve(logos_meta_env_t *me, logos_term ast) {
    logos_env *env = me->env;
    logos_term head, rest, rest2;

    _ensure_tags();
    ast = logos_walk(env, ast);

    /* Scalars and already-runtime values: return as-is */
    if (ast.tag == LOGOS_STRING  || ast.tag == LOGOS_FLOAT ||
        ast.tag == LOGOS_INT     || ast.tag == LOGOS_BOOL  ||
        ast.tag == LOGOS_DURATION || ast.tag == LOGOS_NIL  ||
        ast.tag == LOGOS_VAR)
        return ast;

    if (ast.tag != LOGOS_LIST) return ast;

    head = logos_walk(env, ast.cons->head);
    if (head.tag != LOGOS_STRING) return ast; /* opaque list — runtime value */

    rest = logos_walk(env, ast.cons->tail);

    /* ["var", Name] → logos VAR term (allocate on first use) */
    if (head.s == _TAG_VAR && !logos_is_nil(rest)) {
        logos_term name_t = logos_walk(env, rest.cons->head);
        if (name_t.tag == LOGOS_STRING)
            return _meta_get_var(me, name_t.s);
    }

    /* ["id", Name] → string value (atom) */
    if (head.s == _TAG_ID && !logos_is_nil(rest))
        return logos_walk(env, rest.cons->head);

    /* ["path", Subj, Pred] → graph lookup */
    if (head.s == _TAG_PATH && !logos_is_nil(rest)) {
        logos_term s_t = logos_walk(env, rest.cons->head);
        rest2 = logos_walk(env, rest.cons->tail);
        logos_term p_t = logos_is_nil(rest2) ? logos_nil()
                                              : logos_walk(env, rest2.cons->head);
        if (s_t.tag == LOGOS_STRING && p_t.tag == LOGOS_STRING) {
            logos_term val; double conf;
            if (logos_graph_lookup(env->graph, s_t.s, p_t.s, &val, &conf))
                return val;
        }
        return logos_nil();
    }

    /* ["path-var", VarAst, Pred] → graph lookup with variable subject */
    if (head.s == _TAG_PATHVAR && !logos_is_nil(rest)) {
        logos_term var_ast = logos_walk(env, rest.cons->head);
        rest2 = logos_walk(env, rest.cons->tail);
        logos_term fld_t = logos_is_nil(rest2) ? logos_nil()
                                               : logos_walk(env, rest2.cons->head);
        logos_term subj = logos_walk(env, _meta_resolve(me, var_ast));
        if (subj.tag == LOGOS_STRING && fld_t.tag == LOGOS_STRING) {
            logos_term val; double conf;
            if (logos_graph_lookup(env->graph, subj.s, fld_t.s, &val, &conf))
                return val;
        }
        return logos_nil();
    }

    /* Anything else is already a runtime list value */
    return ast;
}

/* ── Forward declaration (mutual recursion) ─────────────────────────────────── */

static int _meta_call(logos_meta_env_t *me, const char *name,
                       logos_term ast_args);

/* ── Condition evaluation ────────────────────────────────────────────────────── */

static int _meta_eval_cond(logos_meta_env_t *me, logos_term cond) {
    logos_env *env = me->env;
    logos_term tag, rest, name_t, rest2, arg_lst;

    _ensure_tags();
    cond = logos_walk(env, cond);
    if (cond.tag != LOGOS_LIST) return 0;

    tag  = logos_walk(env, cond.cons->head);
    if (tag.tag != LOGOS_STRING) return 0;
    rest = logos_walk(env, cond.cons->tail);

    /* ["call", Name, Args] */
    if (tag.s == _TAG_CALL) {
        if (logos_is_nil(rest)) return 0;
        name_t  = logos_walk(env, rest.cons->head);
        rest2   = logos_walk(env, rest.cons->tail);
        arg_lst = logos_is_nil(rest2) ? logos_nil()
                                      : logos_walk(env, rest2.cons->head);
        if (name_t.tag != LOGOS_STRING) return 0;
        return _meta_call(me, name_t.s, arg_lst);
    }

    /* ["not-call", Name, Args] — negation-as-failure */
    if (tag.s == _TAG_NOTCALL) {
        if (logos_is_nil(rest)) return 0;
        name_t  = logos_walk(env, rest.cons->head);
        rest2   = logos_walk(env, rest.cons->tail);
        arg_lst = logos_is_nil(rest2) ? logos_nil()
                                      : logos_walk(env, rest2.cons->head);
        if (name_t.tag != LOGOS_STRING) return 0;
        {
            logos_mark_t m = logos_mark(env);
            int ok = _meta_call(me, name_t.s, arg_lst);
            logos_undo(env, m);
            return !ok;
        }
    }

    /* ["cmp", Left, Op, Right] */
    if (tag.s == _TAG_CMP) {
        logos_term lhs_ast, op_t, rhs_ast, lhs, rhs, rest3;
        int op = 4;
        if (logos_is_nil(rest)) return 0;
        lhs_ast = logos_walk(env, rest.cons->head);
        rest2   = logos_walk(env, rest.cons->tail);
        if (logos_is_nil(rest2)) return 0;
        op_t    = logos_walk(env, rest2.cons->head);
        rest3   = logos_walk(env, rest2.cons->tail);
        if (logos_is_nil(rest3)) return 0;
        rhs_ast = logos_walk(env, rest3.cons->head);

        lhs = logos_walk(env, _meta_resolve(me, lhs_ast));
        rhs = logos_walk(env, _meta_resolve(me, rhs_ast));
        if (op_t.tag != LOGOS_STRING) return 0;
        if      (strcmp(op_t.s, ">=") == 0) op = 0;
        else if (strcmp(op_t.s, "<=") == 0) op = 1;
        else if (strcmp(op_t.s, ">")  == 0) op = 2;
        else if (strcmp(op_t.s, "<")  == 0) op = 3;
        else if (strcmp(op_t.s, "=")  == 0) op = 4;
        else if (strcmp(op_t.s, "!=") == 0) op = 5;
        return logos_compare(lhs, op, rhs);
    }

    return 0; /* unknown condition type */
}

/* ── Primitive dispatch table ────────────────────────────────────────────────── */

typedef int (*logos_meta_prim_fn)(logos_env *, logos_term *, int);

static int _mw_equal        (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_equal(e,a[0],a[1]):0;}
static int _mw_true_        (logos_env *e,logos_term *a,int n){(void)a;(void)n;return logos_prim_true(e);}
static int _mw_list_cons    (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_list_cons(e,a[0],a[1],a[2]):0;}
static int _mw_list_empty   (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_list_empty(e,a[0]):0;}
static int _mw_list_head    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_list_head(e,a[0],a[1]):0;}
static int _mw_list_tail    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_list_tail(e,a[0],a[1]):0;}
static int _mw_list_length  (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_list_length(e,a[0],a[1]):0;}
static int _mw_list_nth     (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_list_nth(e,a[0],a[1],a[2]):0;}
static int _mw_list_append  (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_list_append(e,a[0],a[1],a[2]):0;}
static int _mw_list_reverse (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_list_reverse(e,a[0],a[1]):0;}
static int _mw_list_flatten (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_list_flatten(e,a[0],a[1]):0;}
static int _mw_num_add      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_add(e,a[0],a[1],a[2]):0;}
static int _mw_num_sub      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_sub(e,a[0],a[1],a[2]):0;}
static int _mw_num_mul      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_mul(e,a[0],a[1],a[2]):0;}
static int _mw_num_div      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_div(e,a[0],a[1],a[2]):0;}
static int _mw_num_mod      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_mod(e,a[0],a[1],a[2]):0;}
static int _mw_num_abs      (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_num_abs(e,a[0],a[1]):0;}
static int _mw_num_floor    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_num_floor(e,a[0],a[1]):0;}
static int _mw_num_ceil     (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_num_ceil(e,a[0],a[1]):0;}
static int _mw_num_min      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_min(e,a[0],a[1],a[2]):0;}
static int _mw_num_max      (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_num_max(e,a[0],a[1],a[2]):0;}
static int _mw_is_string    (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_is_string(e,a[0]):0;}
static int _mw_is_number    (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_is_number(e,a[0]):0;}
static int _mw_is_list      (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_is_list(e,a[0]):0;}
static int _mw_ground       (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_ground(e,a[0]):0;}
static int _mw_assert_fact  (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_assert_fact(e,a[0],a[1],a[2]):0;}
static int _mw_str_concat   (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_str_concat(e,a[0],a[1],a[2]):0;}
static int _mw_str_length   (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_length(e,a[0],a[1]):0;}
static int _mw_str_char_at  (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_str_char_at(e,a[0],a[1],a[2]):0;}
static int _mw_str_sw       (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_starts_with(e,a[0],a[1]):0;}
static int _mw_str_ew       (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_ends_with(e,a[0],a[1]):0;}
static int _mw_str_slice    (logos_env *e,logos_term *a,int n){return n>=4?logos_prim_str_slice(e,a[0],a[1],a[2],a[3]):0;}
static int _mw_str_to_num   (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_to_number(e,a[0],a[1]):0;}
static int _mw_num_to_str   (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_number_to_str(e,a[0],a[1]):0;}
static int _mw_str_split    (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_str_split(e,a[0],a[1],a[2]):0;}
static int _mw_str_join     (logos_env *e,logos_term *a,int n){return n>=3?logos_prim_str_join(e,a[0],a[1],a[2]):0;}
static int _mw_str_upper    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_upper(e,a[0],a[1]):0;}
static int _mw_str_lower    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_lower(e,a[0],a[1]):0;}
static int _mw_str_trim     (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_trim(e,a[0],a[1]):0;}
static int _mw_str_contains (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_str_contains(e,a[0],a[1]):0;}
static int _mw_char_alpha   (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_char_alpha(e,a[0]):0;}
static int _mw_char_digit   (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_char_digit(e,a[0]):0;}
static int _mw_char_ws      (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_char_whitespace(e,a[0]):0;}
static int _mw_char_alnum   (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_char_alnum(e,a[0]):0;}
static int _mw_char_code    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_char_code(e,a[0],a[1]):0;}
static int _mw_write_output (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_write_output(e,a[0]):0;}
static int _mw_write_line   (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_write_line(e,a[0]):0;}
static int _mw_write_stderr (logos_env *e,logos_term *a,int n){return n>=1?logos_prim_write_stderr(e,a[0]):0;}
static int _mw_read_file    (logos_env *e,logos_term *a,int n){return n>=2?logos_prim_read_file(e,a[0],a[1]):0;}

static struct { const char *name; logos_meta_prim_fn fn; } _prim_table[] = {
    { "equal",           _mw_equal        },
    { "true",            _mw_true_        },
    { "list-cons",       _mw_list_cons    },
    { "list-empty",      _mw_list_empty   },
    { "list-head",       _mw_list_head    },
    { "list-tail",       _mw_list_tail    },
    { "list-length",     _mw_list_length  },
    { "list-nth",        _mw_list_nth     },
    { "list-append",     _mw_list_append  },
    { "list-reverse",    _mw_list_reverse },
    { "list-flatten",    _mw_list_flatten },
    { "num-add",         _mw_num_add      },
    { "num-sub",         _mw_num_sub      },
    { "num-mul",         _mw_num_mul      },
    { "num-div",         _mw_num_div      },
    { "num-mod",         _mw_num_mod      },
    { "num-abs",         _mw_num_abs      },
    { "num-floor",       _mw_num_floor    },
    { "num-ceil",        _mw_num_ceil     },
    { "num-min",         _mw_num_min      },
    { "num-max",         _mw_num_max      },
    { "is-string",       _mw_is_string    },
    { "is-number",       _mw_is_number    },
    { "is-list",         _mw_is_list      },
    { "ground",          _mw_ground       },
    { "assert-fact",     _mw_assert_fact  },
    { "str-concat",      _mw_str_concat   },
    { "str-length",      _mw_str_length   },
    { "str-char-at",     _mw_str_char_at  },
    { "str-starts-with", _mw_str_sw       },
    { "str-ends-with",   _mw_str_ew       },
    { "str-slice",       _mw_str_slice    },
    { "str-to-number",   _mw_str_to_num   },
    { "number-to-str",   _mw_num_to_str   },
    { "str-split",       _mw_str_split    },
    { "str-join",        _mw_str_join     },
    { "str-upper",       _mw_str_upper    },
    { "str-lower",       _mw_str_lower    },
    { "str-trim",        _mw_str_trim     },
    { "str-contains",    _mw_str_contains },
    { "char-alpha",      _mw_char_alpha   },
    { "char-digit",      _mw_char_digit   },
    { "char-whitespace", _mw_char_ws      },
    { "char-alnum",      _mw_char_alnum   },
    { "char-code",       _mw_char_code    },
    { "write-output",    _mw_write_output },
    { "write-line",      _mw_write_line   },
    { "write-stderr",    _mw_write_stderr },
    { "read-file",       _mw_read_file    },
    { NULL, NULL }
};

/* Returns >=0 (primitive result) or -1 (not a primitive). */
static int _meta_try_primitive(logos_env *env, const char *name,
                                logos_term *args, int n) {
    int i;
    for (i = 0; _prim_table[i].name; i++)
        if (strcmp(_prim_table[i].name, name) == 0)
            return _prim_table[i].fn(env, args, n);
    return -1;
}

/* ── Try one dynamic rule clause ─────────────────────────────────────────────── */

static int _meta_try_clause(logos_env *env, logos_dyn_rule_t *rule,
                             logos_term *args, int n) {
    logos_meta_env_t me;
    logos_term head_args, conds, cond;
    int j, ok = 1;

    me.env   = env;
    me.count = 0;

    /* Unify head args with call args */
    head_args = logos_walk(env, rule->head_args);
    j = 0;
    while (!logos_is_nil(head_args) && head_args.tag == LOGOS_LIST && j < n) {
        logos_term ast_arg = logos_walk(env, head_args.cons->head);
        logos_term var_t   = _meta_resolve(&me, ast_arg);
        if (!logos_unify(env, var_t, args[j])) { ok = 0; break; }
        head_args = logos_walk(env, head_args.cons->tail);
        j++;
    }
    if (ok && (j != n || !logos_is_nil(head_args))) ok = 0;

    /* Evaluate conditions */
    if (ok) {
        conds = logos_walk(env, rule->conditions);
        while (ok && !logos_is_nil(conds) && conds.tag == LOGOS_LIST) {
            cond = logos_walk(env, conds.cons->head);
            if (!_meta_eval_cond(&me, cond)) ok = 0;
            conds = logos_walk(env, conds.cons->tail);
        }
    }
    return ok;
}

/* ── Dynamic predicate: first-match (leave bindings on success) ──────────────── */

static int _meta_try_dyn_pred(logos_env *env, const char *name,
                               logos_term *args, int n) {
    int i;
    const char *iname = logos_intern(name);
    for (i = 0; i < _n_dyn_rules; i++) {
        if (_dyn_rules[i].name != iname) continue;
        {
            logos_mark_t mark = logos_mark(env);
            if (_meta_try_clause(env, &_dyn_rules[i], args, n))
                return 1;   /* success — leave bindings */
            logos_undo(env, mark);
        }
    }
    return 0;
}

/* ── _meta_call: resolve args, then dispatch to primitive or dynamic rule ─────── */

static int _meta_call(logos_meta_env_t *me, const char *name,
                       logos_term ast_args) {
    logos_term resolved[LOGOS_META_MAX_ARGS];
    logos_term cur;
    int na = 0, r;

    cur = logos_walk(me->env, ast_args);
    while (!logos_is_nil(cur) && cur.tag == LOGOS_LIST
           && na < LOGOS_META_MAX_ARGS) {
        resolved[na++] = _meta_resolve(me, logos_walk(me->env, cur.cons->head));
        cur = logos_walk(me->env, cur.cons->tail);
    }

    r = _meta_try_primitive(me->env, name, resolved, na);
    if (r >= 0) return r;

    return _meta_try_dyn_pred(me->env, name, resolved, na);
}

/* ── Public: register-rule-ast ──────────────────────────────────────────────── */

int logos_prim_register_rule_ast(logos_env *env, logos_term name,
                                  logos_term args, logos_term conds) {
    name  = logos_walk(env, name);
    args  = logos_walk(env, args);
    conds = logos_walk(env, conds);
    if (name.tag != LOGOS_STRING) return 0;
    if (_n_dyn_rules >= LOGOS_MAX_DYN_RULES) {
        fprintf(stderr, "logos_meta: dynamic rule limit exceeded\n");
        return 0;
    }
    _dyn_rules[_n_dyn_rules].name       = logos_intern(name.s);
    _dyn_rules[_n_dyn_rules].head_args  = args;
    _dyn_rules[_n_dyn_rules].conditions = conds;
    _n_dyn_rules++;
    return 1;
}

/* ── Helper: format a cons-list of terms into a text buffer ─────────────────── */

static void _fmt_args(logos_env *env, logos_term args_list,
                       char *buf, int bufsz) {
    int pos = 0, first = 1;
    logos_term cur = logos_walk(env, args_list);
    while (!logos_is_nil(cur) && cur.tag == LOGOS_LIST && pos < bufsz - 4) {
        logos_term a = logos_walk(env, cur.cons->head);
        if (!first) {
            if (pos + 2 < bufsz) { buf[pos++] = ','; buf[pos++] = ' '; }
        }
        if (a.tag == LOGOS_STRING) {
            int len = (int)strlen(a.s);
            if (pos + len < bufsz - 1) { memcpy(buf+pos, a.s, len); pos += len; }
        } else if (a.tag == LOGOS_FLOAT) {
            pos += snprintf(buf+pos, bufsz-pos, "%g", a.f);
        } else if (a.tag == LOGOS_INT) {
            pos += snprintf(buf+pos, bufsz-pos, "%ld", a.i);
        } else {
            if (pos < bufsz - 1) buf[pos++] = '_';
        }
        first = 0;
        cur = logos_walk(env, cur.cons->tail);
    }
    buf[pos] = '\0';
}

/* ── Public: exec-bool-query-ast ────────────────────────────────────────────── */

int logos_prim_exec_bool_query_ast(logos_env *env, logos_term name,
                                    logos_term query_args) {
    logos_term resolved[LOGOS_META_MAX_ARGS];
    int na = 0, i, found = 0;
    double conf = 0.0;
    char text[256], argbuf[200];
    const char *iname;
    logos_meta_env_t me0;

    name       = logos_walk(env, name);
    query_args = logos_walk(env, query_args);
    if (name.tag != LOGOS_STRING) return 0;

    /* Resolve query args */
    me0.env = env; me0.count = 0;
    {
        logos_term cur = query_args;
        while (!logos_is_nil(cur) && cur.tag == LOGOS_LIST
               && na < LOGOS_META_MAX_ARGS) {
            resolved[na++] = _meta_resolve(&me0,
                                logos_walk(env, cur.cons->head));
            cur = logos_walk(env, cur.cons->tail);
        }
    }

    /* Build display text */
    _fmt_args(env, query_args, argbuf, sizeof(argbuf));
    snprintf(text, sizeof(text), "%s(%s)", name.s, argbuf);

    /* Try all matching dynamic rules, accumulate confidence */
    iname = logos_intern(name.s);
    for (i = 0; i < _n_dyn_rules; i++) {
        if (_dyn_rules[i].name != iname) continue;
        {
            logos_mark_t mark   = logos_mark(env);
            double saved_conf   = env->confidence;
            env->confidence     = 1.0;
            if (_meta_try_clause(env, &_dyn_rules[i], resolved, na)) {
                env->confidence = logos_degrade(env->confidence);
                found = 1;
                conf  = logos_disjoin(conf, env->confidence);
            }
            logos_undo(env, mark);
            env->confidence = saved_conf;
        }
    }

    logos_print_bool_result(text, found, conf);
    return 1; /* always succeed — printing is the side effect */
}

/* ── Public: exec-find-query-ast ────────────────────────────────────────────── */

int logos_prim_exec_find_query_ast(logos_env *env, logos_term var_names,
                                    logos_term conds) {
    logos_meta_env_t me;
    logos_term c;
    int ok = 1;
    logos_mark_t mark;
    double saved_conf;

    me.env = env; me.count = 0;
    var_names = logos_walk(env, var_names);
    conds     = logos_walk(env, conds);

    mark       = logos_mark(env);
    saved_conf = env->confidence;
    env->confidence = 1.0;

    /* Evaluate each condition */
    c = conds;
    while (ok && !logos_is_nil(c) && c.tag == LOGOS_LIST) {
        logos_term cond = logos_walk(env, c.cons->head);
        if (!_meta_eval_cond(&me, cond)) ok = 0;
        c = logos_walk(env, c.cons->tail);
    }

    if (ok) {
        /* Collect variable names and their resolved values */
        const char *vnames[LOGOS_META_MAX_VARS];
        logos_term  vvals [LOGOS_META_MAX_VARS];
        int nv = 0;
        logos_term vn = var_names;
        while (!logos_is_nil(vn) && vn.tag == LOGOS_LIST
               && nv < LOGOS_META_MAX_VARS) {
            logos_term vn_ast = logos_walk(env, vn.cons->head);
            logos_term vterm  = logos_walk(env, _meta_resolve(&me, vn_ast));
            /* Extract the variable name string */
            const char *vname = "?";
            if (vn_ast.tag == LOGOS_LIST) {
                logos_term h = logos_walk(env, vn_ast.cons->head);
                logos_term r = logos_walk(env, vn_ast.cons->tail);
                if (h.tag == LOGOS_STRING && !logos_is_nil(r)) {
                    logos_term nt = logos_walk(env, r.cons->head);
                    if (nt.tag == LOGOS_STRING) vname = nt.s;
                }
            } else if (vn_ast.tag == LOGOS_STRING) {
                vname = vn_ast.s;
            }
            vnames[nv] = vname;
            vvals [nv] = vterm;
            nv++;
            vn = logos_walk(env, vn.cons->tail);
        }
        env->confidence = logos_degrade(env->confidence);
        logos_print_find_row(vnames, vvals, nv, env->confidence);
    }

    logos_undo(env, mark);
    env->confidence = saved_conf;
    return 1; /* always succeed */
}
