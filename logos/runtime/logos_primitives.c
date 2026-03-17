#include "logos_primitives.h"
#include <math.h>
#include <string.h>

/* ── Numeric coercion helper ─────────────────────────────────────────────── */

static int _to_num(logos_env *env, logos_term t, double *out) {
    t = logos_walk(env, t);
    switch (t.tag) {
        case LOGOS_INT:      *out = (double)t.i; return 1;
        case LOGOS_FLOAT:    *out = t.f;         return 1;
        case LOGOS_DURATION: *out = t.f;         return 1;
        default:             return 0;
    }
}

/* Always return FLOAT for computed numeric results.
 * This matches the Logos interpreter behaviour where arithmetic yields floats,
 * so that a result can unify with the float literals the parser produces. */
static logos_term _make_num(double v) {
    return logos_float(v);
}

/* ── List helpers ────────────────────────────────────────────────────────── */

static logos_term _append_lists(logos_env *env, logos_term a, logos_term b) {
    a = logos_walk(env, a);
    if (a.tag == LOGOS_NIL)  return b;
    if (a.tag != LOGOS_LIST) return b;   /* malformed */
    return logos_list_cons(a.cons->head,
                           _append_lists(env, a.cons->tail, b));
}

static logos_term _reverse_list(logos_env *env, logos_term l) {
    logos_term acc = logos_nil();
    logos_term cur = logos_walk(env, l);
    while (cur.tag == LOGOS_LIST) {
        acc = logos_list_cons(cur.cons->head, acc);
        cur = logos_walk(env, cur.cons->tail);
    }
    return acc;
}

static logos_term _flatten_list(logos_env *env, logos_term l);

static logos_term _flatten_append(logos_env *env,
                                  logos_term a, logos_term b) {
    a = logos_walk(env, a);
    if (a.tag == LOGOS_NIL)  return b;
    if (a.tag != LOGOS_LIST) return b;
    return logos_list_cons(a.cons->head,
                           _flatten_append(env, a.cons->tail, b));
}

static logos_term _flatten_list(logos_env *env, logos_term l) {
    l = logos_walk(env, l);
    if (l.tag == LOGOS_NIL)  return logos_nil();
    if (l.tag != LOGOS_LIST) return logos_list_cons(l, logos_nil());
    logos_term head = logos_walk(env, l.cons->head);
    logos_term rest = _flatten_list(env, l.cons->tail);
    if (head.tag == LOGOS_LIST || head.tag == LOGOS_NIL)
        return _flatten_append(env, _flatten_list(env, head), rest);
    return logos_list_cons(head, rest);
}

/* ── Equality / truth ────────────────────────────────────────────────────── */

int logos_prim_equal(logos_env *env, logos_term a, logos_term b) {
    return logos_unify(env, a, b);
}

int logos_prim_true(logos_env *env) {
    (void)env;
    return 1;
}

/* ── List primitives ─────────────────────────────────────────────────────── */

int logos_prim_list_cons(logos_env *env, logos_term h, logos_term t,
                         logos_term l) {
    logos_term lw = logos_walk(env, l);
    logos_mark_t m;

    if (lw.tag == LOGOS_LIST) {
        /* Decompose: unify H with head, T with tail */
        m = logos_mark(env);
        if (!logos_unify(env, h, lw.cons->head)) { logos_undo(env, m); return 0; }
        if (!logos_unify(env, t, lw.cons->tail))  { logos_undo(env, m); return 0; }
        return 1;
    }
    if (lw.tag == LOGOS_NIL) return 0;   /* empty list has no head/tail */

    /* L is unbound — construct [H|T] and unify with L */
    {
        logos_term hw = logos_walk(env, h);
        logos_term tw = logos_walk(env, t);
        logos_term cell = logos_list_cons(hw, tw);
        return logos_unify(env, l, cell);
    }
}

int logos_prim_list_empty(logos_env *env, logos_term l) {
    l = logos_walk(env, l);
    if (l.tag == LOGOS_NIL)  return 1;
    if (l.tag == LOGOS_VAR)  return logos_unify(env, l, logos_nil());
    return 0;
}

int logos_prim_list_head(logos_env *env, logos_term h, logos_term l) {
    l = logos_walk(env, l);
    if (l.tag != LOGOS_LIST) return 0;
    return logos_unify(env, h, l.cons->head);
}

int logos_prim_list_tail(logos_env *env, logos_term t, logos_term l) {
    l = logos_walk(env, l);
    if (l.tag != LOGOS_LIST) return 0;
    return logos_unify(env, t, l.cons->tail);
}

int logos_prim_list_length(logos_env *env, logos_term l, logos_term n) {
    logos_term cur = logos_walk(env, l);
    long len = 0;
    while (cur.tag == LOGOS_LIST) {
        len++;
        cur = logos_walk(env, cur.cons->tail);
    }
    if (cur.tag != LOGOS_NIL) return 0;   /* not a proper list */
    return logos_unify(env, n, logos_int(len));
}

int logos_prim_list_nth(logos_env *env, logos_term l, logos_term n,
                        logos_term x) {
    logos_term nw = logos_walk(env, n);
    logos_term cur;
    long idx;
    if (nw.tag != LOGOS_INT) return 0;
    idx = nw.i;
    cur = logos_walk(env, l);
    while (idx > 0 && cur.tag == LOGOS_LIST) {
        cur = logos_walk(env, cur.cons->tail);
        idx--;
    }
    if (cur.tag != LOGOS_LIST) return 0;
    return logos_unify(env, x, cur.cons->head);
}

int logos_prim_list_append(logos_env *env, logos_term l1, logos_term l2,
                           logos_term l3) {
    logos_term result = _append_lists(env, l1, l2);
    return logos_unify(env, l3, result);
}

int logos_prim_list_reverse(logos_env *env, logos_term l, logos_term r) {
    logos_term result = _reverse_list(env, l);
    return logos_unify(env, r, result);
}

int logos_prim_list_flatten(logos_env *env, logos_term l, logos_term f) {
    logos_term result = _flatten_list(env, l);
    return logos_unify(env, f, result);
}

/* ── Numeric primitives ──────────────────────────────────────────────────── */

int logos_prim_num_add(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    return logos_unify(env, c, _make_num(av + bv));
}

int logos_prim_num_sub(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    return logos_unify(env, c, _make_num(av - bv));
}

int logos_prim_num_mul(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    return logos_unify(env, c, _make_num(av * bv));
}

int logos_prim_num_div(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    if (bv == 0.0) return 0;
    return logos_unify(env, c, _make_num(av / bv));
}

int logos_prim_num_mod(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    if (bv == 0.0) return 0;
    return logos_unify(env, c, _make_num(fmod(av, bv)));
}

int logos_prim_num_abs(logos_env *env, logos_term a, logos_term b) {
    double av;
    if (!_to_num(env, a, &av)) return 0;
    return logos_unify(env, b, _make_num(fabs(av)));
}

int logos_prim_num_floor(logos_env *env, logos_term a, logos_term b) {
    double av;
    if (!_to_num(env, a, &av)) return 0;
    return logos_unify(env, b, logos_int((long)floor(av)));
}

int logos_prim_num_ceil(logos_env *env, logos_term a, logos_term b) {
    double av;
    if (!_to_num(env, a, &av)) return 0;
    return logos_unify(env, b, logos_int((long)ceil(av)));
}

int logos_prim_num_min(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    return logos_unify(env, c, _make_num(av < bv ? av : bv));
}

int logos_prim_num_max(logos_env *env, logos_term a, logos_term b,
                       logos_term c) {
    double av, bv;
    if (!_to_num(env, a, &av) || !_to_num(env, b, &bv)) return 0;
    return logos_unify(env, c, _make_num(av > bv ? av : bv));
}

/* ── Type-check primitives ───────────────────────────────────────────────── */

int logos_prim_is_string(logos_env *env, logos_term t) {
    t = logos_walk(env, t);
    return t.tag == LOGOS_STRING;
}

int logos_prim_is_number(logos_env *env, logos_term t) {
    t = logos_walk(env, t);
    return t.tag == LOGOS_INT || t.tag == LOGOS_FLOAT || t.tag == LOGOS_DURATION;
}

int logos_prim_is_list(logos_env *env, logos_term t) {
    t = logos_walk(env, t);
    return t.tag == LOGOS_LIST || t.tag == LOGOS_NIL;
}

int logos_prim_ground(logos_env *env, logos_term t) {
    t = logos_walk(env, t);
    if (t.tag == LOGOS_VAR) return 0;
    if (t.tag == LOGOS_LIST) {
        logos_term cur = t;
        while (cur.tag == LOGOS_LIST) {
            if (!logos_prim_ground(env, cur.cons->head)) return 0;
            cur = logos_walk(env, cur.cons->tail);
        }
        return 1;
    }
    return 1;
}
