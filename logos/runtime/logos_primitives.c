#include "logos_primitives.h"
#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
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

/* ── String helpers ──────────────────────────────────────────────────────── */

/* Make a logos_term STRING from an already-interned pointer. */
static logos_term _str_term(const char *interned) {
    logos_term t;
    t.tag = LOGOS_STRING;
    t.s   = interned;
    return t;
}

/* Intern a NUL-terminated buf of given length (not NUL-counted). */
static const char *_intern_buf(const char *p, size_t len) {
    char *tmp = (char *)malloc(len + 1);
    if (!tmp) return "";
    memcpy(tmp, p, len);
    tmp[len] = '\0';
    const char *r = logos_intern(tmp);
    free(tmp);
    return r;
}

/* ── String primitives ───────────────────────────────────────────────────── */

int logos_prim_str_concat(logos_env *env, logos_term a, logos_term b,
                          logos_term c) {
    a = logos_walk(env, a);
    b = logos_walk(env, b);
    if (a.tag != LOGOS_STRING || b.tag != LOGOS_STRING) return 0;
    size_t la = strlen(a.s), lb = strlen(b.s);
    char *buf = (char *)malloc(la + lb + 1);
    if (!buf) return 0;
    memcpy(buf, a.s, la);
    memcpy(buf + la, b.s, lb);
    buf[la + lb] = '\0';
    logos_term res = _str_term(logos_intern(buf));
    free(buf);
    return logos_unify(env, c, res);
}

int logos_prim_str_length(logos_env *env, logos_term s, logos_term n) {
    s = logos_walk(env, s);
    if (s.tag != LOGOS_STRING) return 0;
    return logos_unify(env, n, logos_float((double)strlen(s.s)));
}

int logos_prim_str_char_at(logos_env *env, logos_term s, logos_term idx,
                           logos_term ch) {
    s   = logos_walk(env, s);
    idx = logos_walk(env, idx);
    if (s.tag != LOGOS_STRING) return 0;
    long i;
    if      (idx.tag == LOGOS_INT)   i = idx.i;
    else if (idx.tag == LOGOS_FLOAT) i = (long)idx.f;
    else return 0;
    size_t len = strlen(s.s);
    if (i < 0 || (size_t)i >= len) return 0;
    char buf[2] = { s.s[i], '\0' };
    return logos_unify(env, ch, _str_term(logos_intern(buf)));
}

int logos_prim_str_starts_with(logos_env *env, logos_term s, logos_term prefix) {
    s      = logos_walk(env, s);
    prefix = logos_walk(env, prefix);
    if (s.tag != LOGOS_STRING || prefix.tag != LOGOS_STRING) return 0;
    size_t plen = strlen(prefix.s);
    return strncmp(s.s, prefix.s, plen) == 0;
}

int logos_prim_str_ends_with(logos_env *env, logos_term s, logos_term suffix) {
    s      = logos_walk(env, s);
    suffix = logos_walk(env, suffix);
    if (s.tag != LOGOS_STRING || suffix.tag != LOGOS_STRING) return 0;
    size_t slen  = strlen(s.s);
    size_t sflen = strlen(suffix.s);
    if (sflen > slen) return 0;
    return strcmp(s.s + slen - sflen, suffix.s) == 0;
}

int logos_prim_str_slice(logos_env *env, logos_term s, logos_term start,
                         logos_term end_t, logos_term result) {
    s     = logos_walk(env, s);
    start = logos_walk(env, start);
    end_t = logos_walk(env, end_t);
    if (s.tag != LOGOS_STRING) return 0;
    long st, en;
    if      (start.tag == LOGOS_INT)   st = start.i;
    else if (start.tag == LOGOS_FLOAT) st = (long)start.f;
    else return 0;
    if      (end_t.tag == LOGOS_INT)   en = end_t.i;
    else if (end_t.tag == LOGOS_FLOAT) en = (long)end_t.f;
    else return 0;
    size_t len = strlen(s.s);
    if (st < 0)           st = 0;
    if ((size_t)en > len) en = (long)len;
    if (st > en)          st = en;
    return logos_unify(env, result,
                       _str_term(_intern_buf(s.s + st, (size_t)(en - st))));
}

int logos_prim_str_to_number(logos_env *env, logos_term s, logos_term n) {
    s = logos_walk(env, s);
    if (s.tag != LOGOS_STRING) return 0;
    char *end;
    double v = strtod(s.s, &end);
    if (end == s.s || *end != '\0') return 0;
    return logos_unify(env, n, logos_float(v));
}

int logos_prim_number_to_str(logos_env *env, logos_term n, logos_term s) {
    n = logos_walk(env, n);
    char buf[64];
    if (n.tag == LOGOS_INT) {
        snprintf(buf, sizeof(buf), "%ld", n.i);
    } else if (n.tag == LOGOS_FLOAT) {
        long iv = (long)n.f;
        if ((double)iv == n.f) snprintf(buf, sizeof(buf), "%ld", iv);
        else                   snprintf(buf, sizeof(buf), "%g",  n.f);
    } else return 0;
    return logos_unify(env, s, _str_term(logos_intern(buf)));
}

int logos_prim_str_split(logos_env *env, logos_term s, logos_term sep,
                         logos_term lst) {
    s   = logos_walk(env, s);
    sep = logos_walk(env, sep);
    if (s.tag != LOGOS_STRING || sep.tag != LOGOS_STRING) return 0;

    const char *str = s.s;
    logos_term result;

    if (sep.s[0] == '\0') {
        /* Split into individual characters */
        size_t n = strlen(str);
        result = logos_nil();
        char cbuf[2] = { 0, 0 };
        int i;
        for (i = (int)n - 1; i >= 0; i--) {
            cbuf[0] = str[i];
            result  = logos_list_cons(_str_term(logos_intern(cbuf)), result);
        }
    } else {
        const char *sep_str = sep.s;
        size_t sep_len = strlen(sep_str);
        /* Count parts */
        int nparts = 1;
        const char *p = str;
        const char *q;
        while ((q = strstr(p, sep_str)) != NULL) { nparts++; p = q + sep_len; }
        /* Collect interned part pointers */
        const char **parts = (const char **)malloc((size_t)nparts * sizeof(char *));
        if (!parts) return 0;
        int n = 0;
        p = str;
        while ((q = strstr(p, sep_str)) != NULL && n < nparts - 1) {
            parts[n++] = _intern_buf(p, (size_t)(q - p));
            p = q + sep_len;
        }
        parts[n++] = logos_intern(p);
        /* Build cons list back-to-front */
        result = logos_nil();
        for (int i = n - 1; i >= 0; i--)
            result = logos_list_cons(_str_term(parts[i]), result);
        free(parts);
    }
    return logos_unify(env, lst, result);
}

int logos_prim_str_join(logos_env *env, logos_term lst, logos_term sep,
                        logos_term result) {
    lst = logos_walk(env, lst);
    sep = logos_walk(env, sep);
    if (sep.tag != LOGOS_STRING) return 0;
    const char *sep_str = sep.s;
    size_t sep_len = strlen(sep_str);
    /* First pass: compute total length */
    size_t total = 0;
    int    count = 0;
    logos_term cur = lst;
    while (cur.tag == LOGOS_LIST) {
        logos_term elem = logos_walk(env, cur.cons->head);
        if (elem.tag != LOGOS_STRING) return 0;
        if (count > 0) total += sep_len;
        total += strlen(elem.s);
        count++;
        cur = logos_walk(env, cur.cons->tail);
    }
    if (cur.tag != LOGOS_NIL) return 0;
    /* Second pass: fill buffer */
    char *buf = (char *)malloc(total + 1);
    if (!buf) return 0;
    char *p = buf;
    int first = 1;
    cur = lst;
    while (cur.tag == LOGOS_LIST) {
        logos_term elem = logos_walk(env, cur.cons->head);
        if (!first) { memcpy(p, sep_str, sep_len); p += sep_len; }
        size_t len = strlen(elem.s);
        memcpy(p, elem.s, len);
        p += len;
        first = 0;
        cur = logos_walk(env, cur.cons->tail);
    }
    *p = '\0';
    logos_term res = _str_term(logos_intern(buf));
    free(buf);
    return logos_unify(env, result, res);
}

int logos_prim_str_upper(logos_env *env, logos_term s, logos_term u) {
    s = logos_walk(env, s);
    if (s.tag != LOGOS_STRING) return 0;
    size_t len = strlen(s.s);
    char *buf = (char *)malloc(len + 1);
    if (!buf) return 0;
    size_t i;
    for (i = 0; i <= len; i++) buf[i] = (char)toupper((unsigned char)s.s[i]);
    logos_term res = _str_term(logos_intern(buf));
    free(buf);
    return logos_unify(env, u, res);
}

int logos_prim_str_lower(logos_env *env, logos_term s, logos_term l) {
    s = logos_walk(env, s);
    if (s.tag != LOGOS_STRING) return 0;
    size_t len = strlen(s.s);
    char *buf = (char *)malloc(len + 1);
    if (!buf) return 0;
    size_t i;
    for (i = 0; i <= len; i++) buf[i] = (char)tolower((unsigned char)s.s[i]);
    logos_term res = _str_term(logos_intern(buf));
    free(buf);
    return logos_unify(env, l, res);
}

int logos_prim_str_trim(logos_env *env, logos_term s, logos_term t) {
    s = logos_walk(env, s);
    if (s.tag != LOGOS_STRING) return 0;
    const char *p = s.s;
    while (*p && isspace((unsigned char)*p)) p++;
    const char *end = p + strlen(p);
    while (end > p && isspace((unsigned char)end[-1])) end--;
    return logos_unify(env, t, _str_term(_intern_buf(p, (size_t)(end - p))));
}

int logos_prim_str_contains(logos_env *env, logos_term s, logos_term sub) {
    s   = logos_walk(env, s);
    sub = logos_walk(env, sub);
    if (s.tag != LOGOS_STRING || sub.tag != LOGOS_STRING) return 0;
    return strstr(s.s, sub.s) != NULL;
}

/* ── Character class predicates ──────────────────────────────────────────── */

static int _is_single_char_str(logos_env *env, logos_term t, char *out) {
    t = logos_walk(env, t);
    if (t.tag != LOGOS_STRING || t.s[0] == '\0' || t.s[1] != '\0') return 0;
    *out = t.s[0];
    return 1;
}

/* ── Dynamic fact assertion ──────────────────────────────────────────────── */

int logos_prim_assert_fact(logos_env *env, logos_term subject,
                            logos_term predicate, logos_term value) {
    subject   = logos_walk(env, subject);
    predicate = logos_walk(env, predicate);
    value     = logos_walk(env, value);
    if (subject.tag != LOGOS_STRING || predicate.tag != LOGOS_STRING) return 0;
    logos_graph_assert(env->graph, subject.s, predicate.s, value, 1.0);
    return 1;
}

/* ── Character class predicates ──────────────────────────────────────────── */

int logos_prim_char_alpha(logos_env *env, logos_term c) {
    char ch; return _is_single_char_str(env, c, &ch) && isalpha((unsigned char)ch);
}
int logos_prim_char_digit(logos_env *env, logos_term c) {
    char ch; return _is_single_char_str(env, c, &ch) && isdigit((unsigned char)ch);
}
int logos_prim_char_whitespace(logos_env *env, logos_term c) {
    char ch; return _is_single_char_str(env, c, &ch) && isspace((unsigned char)ch);
}
int logos_prim_char_alnum(logos_env *env, logos_term c) {
    char ch; return _is_single_char_str(env, c, &ch) && isalnum((unsigned char)ch);
}
int logos_prim_char_code(logos_env *env, logos_term c, logos_term n) {
    char ch;
    if (!_is_single_char_str(env, c, &ch)) return 0;
    return logos_unify(env, n, logos_float((double)(unsigned char)ch));
}
