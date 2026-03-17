#include "logos_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ── String interning ───────────────────────────────────────────────────────── */

#define INTERN_SLOTS 1024
static const char *_intern_table[INTERN_SLOTS];

const char *logos_intern(const char *s) {
    unsigned int h = 0;
    const char *p;
    int i, idx;
    char *copy;

    for (p = s; *p; p++)
        h = h * 31 + (unsigned char)*p;

    /* linear probe */
    for (i = 0; i < INTERN_SLOTS; i++) {
        idx = (int)((h + (unsigned)i) % INTERN_SLOTS);
        if (_intern_table[idx] == NULL) {
            copy = (char *)malloc(strlen(s) + 1);
            if (!copy) return s;
            strcpy(copy, s);
            _intern_table[idx] = copy;
            return _intern_table[idx];
        }
        if (strcmp(_intern_table[idx], s) == 0)
            return _intern_table[idx];
    }
    /* table full — fall back to heap string (no dedup) */
    copy = (char *)malloc(strlen(s) + 1);
    if (!copy) return s;
    strcpy(copy, s);
    return copy;
}

/* ── Term constructors ──────────────────────────────────────────────────────── */

logos_term logos_int(long i) {
    logos_term t;
    t.tag = LOGOS_INT;
    t.i   = i;
    return t;
}

logos_term logos_float(double f) {
    logos_term t;
    t.tag = LOGOS_FLOAT;
    t.f   = f;
    return t;
}

logos_term logos_string(const char *s) {
    logos_term t;
    t.tag = LOGOS_STRING;
    t.s   = logos_intern(s);
    return t;
}

logos_term logos_duration(double secs) {
    logos_term t;
    t.tag = LOGOS_DURATION;
    t.f   = secs;
    return t;
}

/* ── Variables ──────────────────────────────────────────────────────────────── */

logos_term logos_alloc_var(logos_env *env) {
    logos_term t, none;
    int id = env->bindings.num_vars++;
    t.tag    = LOGOS_VAR;
    t.var_id = id;
    none.tag = LOGOS_NONE;
    none.i   = 0;
    env->bindings.bindings[id] = none;
    return t;
}

logos_term logos_walk(logos_env *env, logos_term t) {
    logos_term b;
    while (t.tag == LOGOS_VAR) {
        b = env->bindings.bindings[t.var_id];
        if (b.tag == LOGOS_NONE) return t;   /* unbound */
        t = b;
    }
    return t;
}

/* ── Backtracking ───────────────────────────────────────────────────────────── */

logos_mark_t logos_mark(logos_env *env) {
    return env->trail.top;
}

void logos_undo(logos_env *env, logos_mark_t mark) {
    logos_term none;
    none.tag = LOGOS_NONE;
    none.i   = 0;
    while (env->trail.top > mark) {
        int var_id = env->trail.entries[--env->trail.top];
        env->bindings.bindings[var_id] = none;
    }
}

/* ── Unification ────────────────────────────────────────────────────────────── */

int logos_unify(logos_env *env, logos_term a, logos_term b) {
    a = logos_walk(env, a);
    b = logos_walk(env, b);

    if (a.tag == LOGOS_VAR) {
        env->bindings.bindings[a.var_id] = b;
        if (env->trail.top < LOGOS_MAX_TRAIL)
            env->trail.entries[env->trail.top++] = a.var_id;
        return 1;
    }
    if (b.tag == LOGOS_VAR) {
        env->bindings.bindings[b.var_id] = a;
        if (env->trail.top < LOGOS_MAX_TRAIL)
            env->trail.entries[env->trail.top++] = b.var_id;
        return 1;
    }

    if (a.tag != b.tag) return 0;

    switch (a.tag) {
        case LOGOS_INT:      return a.i == b.i;
        case LOGOS_FLOAT:    return a.f == b.f;
        case LOGOS_STRING:   return a.s == b.s;   /* interned → pointer eq */
        case LOGOS_BOOL:     return a.i == b.i;
        case LOGOS_DURATION: return a.f == b.f;
        case LOGOS_NONE:     return 1;
        default:             return 0;
    }
}

/* ── Graph ──────────────────────────────────────────────────────────────────── */

void logos_graph_assert(logos_graph *g, const char *subj, const char *pred,
                        logos_term val, double conf) {
    logos_fact *f;
    if (g->count >= LOGOS_MAX_FACTS) return;
    f            = &g->facts[g->count++];
    f->subject   = logos_intern(subj);
    f->predicate = logos_intern(pred);
    f->value     = val;
    f->confidence = conf;
}

int logos_graph_lookup(logos_graph *g, const char *subj, const char *pred,
                       logos_term *out, double *conf_out) {
    const char *isubj = logos_intern(subj);
    const char *ipred = logos_intern(pred);
    double best = -1.0;
    int i, found = 0;

    for (i = 0; i < g->count; i++) {
        logos_fact *f = &g->facts[i];
        if (f->subject == isubj && f->predicate == ipred) {
            if (f->confidence > best) {
                best      = f->confidence;
                *out      = f->value;
                *conf_out = f->confidence;
                found     = 1;
            }
        }
    }
    return found;
}

int logos_graph_scan(logos_graph *g, const char *pred, logos_env *env,
                     logos_scan_cb cb, logos_cont k) {
    const char *ipred = logos_intern(pred);
    int i, result = 0;

    for (i = 0; i < g->count; i++) {
        logos_fact *f = &g->facts[i];
        if (f->predicate == ipred) {
            if (cb(env, f->subject, f->value, f->confidence, k))
                result = 1;
        }
    }
    return result;
}

/* ── Confidence arithmetic ──────────────────────────────────────────────────── */

double logos_conjoin(double a, double b)  { return a * b; }
double logos_disjoin(double a, double b)  { return 1.0 - (1.0 - a) * (1.0 - b); }
double logos_degrade(double c)            { return c * 0.95; }

/* ── Comparison ─────────────────────────────────────────────────────────────── */

static double _term_to_num(logos_term t, int *ok) {
    *ok = 1;
    switch (t.tag) {
        case LOGOS_INT:      return (double)t.i;
        case LOGOS_FLOAT:    return t.f;
        case LOGOS_DURATION: return t.f;
        default: *ok = 0; return 0.0;
    }
}

int logos_compare(logos_term l, int op, logos_term r) {
    int ok_l, ok_r;
    double nl, nr;

    /* String comparison */
    if (l.tag == LOGOS_STRING && r.tag == LOGOS_STRING) {
        switch (op) {
            case 4: return l.s == r.s;          /* = */
            case 5: return l.s != r.s;          /* != */
            default: return 0;
        }
    }

    /* Boolean comparison */
    if (l.tag == LOGOS_BOOL && r.tag == LOGOS_BOOL) {
        switch (op) {
            case 4: return l.i == r.i;
            case 5: return l.i != r.i;
            default: return 0;
        }
    }

    /* Numeric / Duration comparison */
    nl = _term_to_num(l, &ok_l);
    nr = _term_to_num(r, &ok_r);
    if (!ok_l || !ok_r) return 0;

    switch (op) {
        case 0: return nl >= nr;
        case 1: return nl <= nr;
        case 2: return nl >  nr;
        case 3: return nl <  nr;
        case 4: return nl == nr;
        case 5: return nl != nr;
        default: return 0;
    }
}

/* ── Built-in continuations ─────────────────────────────────────────────────── */

int k_bool_capture(logos_env *env) {
    if (env->capture_found && env->capture_conf) {
        int    *found = (int    *)env->capture_found;
        double *conf  = (double *)env->capture_conf;
        *conf  = logos_disjoin(*conf, env->confidence);
        *found = 1;
    }
    return 0;   /* 0 = "continue exploring" — all proof paths are tried */
}

int k_naf_capture(logos_env *env) {
    if (env->capture_found) {
        int *found = (int *)env->capture_found;
        *found = 1;
    }
    return 0;
}

/* ── Output ─────────────────────────────────────────────────────────────────── */

static void _print_term(logos_term t) {
    switch (t.tag) {
        case LOGOS_INT:      printf("%ld", t.i);                  break;
        case LOGOS_FLOAT:    printf("%g",  t.f);                  break;
        case LOGOS_STRING:   printf("%s",  t.s);                  break;
        case LOGOS_BOOL:     printf("%s",  t.i ? "true":"false"); break;
        case LOGOS_DURATION: printf("%.6g secs", t.f);            break;
        case LOGOS_NONE:     printf("_");                          break;
        default:             printf("?");                          break;
    }
}

void logos_print_bool_result(const char *text, int found, double conf) {
    printf("%s: %s", text, found ? "true" : "false");
    if (found) printf("  [confidence: %.3f]", conf);
    printf("\n");
}

void logos_print_find_row(const char **var_names, logos_term *vals,
                          int n_vars, double conf) {
    int i;
    for (i = 0; i < n_vars; i++) {
        if (i > 0) printf(", ");
        printf("%s=", var_names[i]);
        _print_term(vals[i]);
    }
    printf("  [confidence: %.3f]\n", conf);
}
