#include "logos_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ── String interning ───────────────────────────────────────────────────────── */

#define INTERN_SLOTS 16384   /* power-of-2 for fast modulo */
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
        idx = (int)((h + (unsigned)i) & (INTERN_SLOTS - 1));
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
    /* table full — fall back to undeduped heap string */
    copy = (char *)malloc(strlen(s) + 1);
    if (!copy) return s;
    strcpy(copy, s);
    return copy;
}

/* ── Global cons pool (slab allocator) ──────────────────────────────────────── */

#define CONS_SLAB_SIZE 65536   /* cons cells per slab */

typedef struct _cons_slab {
    logos_cons              cells[CONS_SLAB_SIZE];
    int                     top;
    struct _cons_slab      *next;
} _cons_slab;

static _cons_slab  _first_slab;
static _cons_slab *_cur_slab = NULL;
int                _cons_slab_count = 0;  /* non-static for cross-file debug access */

logos_cons *logos_alloc_cons(void) {
    if (_cur_slab == NULL) {
        /* first call: initialise the embedded slab */
        _first_slab.top  = 0;
        _first_slab.next = NULL;
        _cur_slab = &_first_slab;
    }
    if (_cur_slab->top >= CONS_SLAB_SIZE) {
        /* current slab full: allocate a new heap slab */
        _cons_slab *ns = (_cons_slab *)malloc(sizeof(_cons_slab));
        if (!ns) {
            fprintf(stderr, "logos: out of memory allocating cons slab\n");
            exit(1);
        }
        ns->top  = 0;
        ns->next = NULL;
        _cur_slab->next = ns;
        _cur_slab = ns;
        _cons_slab_count++;
        if (_cons_slab_count % 10 == 0)
            fprintf(stderr, "[logos] cons slabs: %d (%ldM cells)\n",
                    _cons_slab_count,
                    (long)_cons_slab_count * CONS_SLAB_SIZE / 1000000);
        if (_cons_slab_count > 200) {
            fprintf(stderr, "logos: cons slab limit reached (%d slabs = %ldM cells), aborting\n",
                    _cons_slab_count,
                    (long)_cons_slab_count * CONS_SLAB_SIZE / 1000000);
            exit(1);
        }
    }
    return &_cur_slab->cells[_cur_slab->top++];
}

/* ── List constructors ──────────────────────────────────────────────────────── */

logos_term logos_nil(void) {
    logos_term t;
    t.tag = LOGOS_NIL;
    t.i   = 0;
    return t;
}

logos_term logos_list_cons(logos_term head, logos_term tail) {
    logos_cons *cell = logos_alloc_cons();
    logos_term  t;
    cell->head = head;
    cell->tail = tail;
    t.tag  = LOGOS_LIST;
    t.cons = cell;
    return t;
}

logos_term logos_list_from_array(logos_term *terms, int n) {
    logos_term result = logos_nil();
    int i;
    for (i = n - 1; i >= 0; i--)
        result = logos_list_cons(terms[i], result);
    return result;
}

int logos_is_nil(logos_term t)  { return t.tag == LOGOS_NIL;  }
int logos_is_list(logos_term t) { return t.tag == LOGOS_LIST; }

/* ── Scalar term constructors ───────────────────────────────────────────────── */

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

/* ── Environment init/teardown ───────────────────────────────────────────────── */

void logos_env_init(logos_env *env) {
    env->bindings.capacity = LOGOS_MAX_VARS;
    env->bindings.num_vars = 0;
    env->bindings.bindings = (logos_term *)calloc(
        (size_t)env->bindings.capacity, sizeof(logos_term));
    if (!env->bindings.bindings) {
        fprintf(stderr, "logos: out of memory initializing bindings\n");
        exit(1);
    }
    env->trail.capacity = LOGOS_MAX_TRAIL;
    env->trail.top      = 0;
    env->trail.entries  = (int *)calloc(
        (size_t)env->trail.capacity, sizeof(int));
    if (!env->trail.entries) {
        fprintf(stderr, "logos: out of memory initializing trail\n");
        exit(1);
    }
}

void logos_env_free(logos_env *env) {
    free(env->bindings.bindings);
    free(env->trail.entries);
    env->bindings.bindings = NULL;
    env->trail.entries     = NULL;
}

/* ── Variables ──────────────────────────────────────────────────────────────── */

logos_term logos_alloc_var(logos_env *env) {
    logos_term t, none;
    int id;
    /* Grow bindings array if needed */
    if (env->bindings.num_vars >= env->bindings.capacity) {
        int new_cap = env->bindings.capacity * 2;
        logos_term *new_b = (logos_term *)realloc(
            env->bindings.bindings, (size_t)new_cap * sizeof(logos_term));
        if (!new_b) {
            fprintf(stderr, "logos: out of memory growing bindings\n");
            exit(1);
        }
        /* Zero-initialize the new portion */
        memset(new_b + env->bindings.capacity, 0,
               (size_t)(new_cap - env->bindings.capacity) * sizeof(logos_term));
        env->bindings.bindings = new_b;
        env->bindings.capacity = new_cap;
    }
    id = env->bindings.num_vars++;
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
    logos_mark_t m;
    m.trail_top = env->trail.top;
    m.num_vars  = env->bindings.num_vars;
    m.cont_ctx  = env->cont_ctx;
    return m;
}

void logos_undo(logos_env *env, logos_mark_t mark) {
    logos_term none;
    none.tag = LOGOS_NONE;
    none.i   = 0;
    while (env->trail.top > mark.trail_top) {
        int var_id = env->trail.entries[--env->trail.top];
        env->bindings.bindings[var_id] = none;
    }
    env->bindings.num_vars = mark.num_vars;
    env->cont_ctx          = mark.cont_ctx;
}

/* ── Unification ────────────────────────────────────────────────────────────── */

int logos_unify(logos_env *env, logos_term a, logos_term b) {
    logos_mark_t m;
    a = logos_walk(env, a);
    b = logos_walk(env, b);

    if (a.tag == LOGOS_VAR) {
        env->bindings.bindings[a.var_id] = b;
        if (env->trail.top >= env->trail.capacity) {
            int new_cap = env->trail.capacity * 2;
            int *new_t  = (int *)realloc(env->trail.entries,
                                         (size_t)new_cap * sizeof(int));
            if (!new_t) { fprintf(stderr, "logos: out of memory growing trail\n"); exit(1); }
            env->trail.entries  = new_t;
            env->trail.capacity = new_cap;
        }
        env->trail.entries[env->trail.top++] = a.var_id;
        return 1;
    }
    if (b.tag == LOGOS_VAR) {
        env->bindings.bindings[b.var_id] = a;
        if (env->trail.top >= env->trail.capacity) {
            int new_cap = env->trail.capacity * 2;
            int *new_t  = (int *)realloc(env->trail.entries,
                                         (size_t)new_cap * sizeof(int));
            if (!new_t) { fprintf(stderr, "logos: out of memory growing trail\n"); exit(1); }
            env->trail.entries  = new_t;
            env->trail.capacity = new_cap;
        }
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
        case LOGOS_NIL:      return 1;            /* nil = nil */
        case LOGOS_LIST:
            /* Structural unification; take a mark so partial success is undone */
            m = logos_mark(env);
            if (!logos_unify(env, a.cons->head, b.cons->head)) {
                logos_undo(env, m);
                return 0;
            }
            if (!logos_unify(env, a.cons->tail, b.cons->tail)) {
                logos_undo(env, m);
                return 0;
            }
            return 1;
        default: return 0;
    }
}

/* ── Graph ──────────────────────────────────────────────────────────────────── */

void logos_graph_assert(logos_graph *g, const char *subj, const char *pred,
                        logos_term val, double conf) {
    logos_fact *f;
    if (g->count >= LOGOS_MAX_FACTS) return;
    f             = &g->facts[g->count++];
    f->subject    = logos_intern(subj);
    f->predicate  = logos_intern(pred);
    f->value      = val;
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
            case 4: return l.s == r.s;
            case 5: return l.s != r.s;
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
    return 1;  /* stop after first solution — bool queries ask "does it hold?", not "how many ways?" */
}

int k_naf_capture(logos_env *env) {
    if (env->capture_found) {
        int *found = (int *)env->capture_found;
        *found = 1;
    }
    return 0;
}

/* ── Output ─────────────────────────────────────────────────────────────────── */

/* Set to 1 after write-output is called (compiler mode) so that bool/find
 * query results are redirected to stderr rather than mixing with C output. */
int logos_query_to_stderr = 0;

void logos_print_term(logos_term t) {
    logos_term cur;
    int first;
    switch (t.tag) {
        case LOGOS_INT:      printf("%ld",  t.i);                  break;
        case LOGOS_FLOAT:    printf("%g",   t.f);                  break;
        case LOGOS_STRING:   printf("%s",   t.s);                  break;
        case LOGOS_BOOL:     printf("%s",   t.i ? "true":"false"); break;
        case LOGOS_DURATION: printf("%.6g secs", t.f);             break;
        case LOGOS_NONE:     printf("_");                           break;
        case LOGOS_NIL:      printf("[]");                          break;
        case LOGOS_LIST:
            printf("[");
            cur   = t;
            first = 1;
            while (cur.tag == LOGOS_LIST) {
                if (!first) printf(", ");
                logos_print_term(cur.cons->head);
                cur   = cur.cons->tail;
                first = 0;
            }
            if (cur.tag != LOGOS_NIL) {
                printf(" | ");
                logos_print_term(cur);
            }
            printf("]");
            break;
        default: printf("?"); break;
    }
}

void logos_print_bool_result(const char *text, int found, double conf) {
    FILE *out = logos_query_to_stderr ? stderr : stdout;
    fprintf(out, "%s: %s", text, found ? "true" : "false");
    if (found) fprintf(out, "  [confidence: %.3f]", conf);
    fprintf(out, "\n");
}

void logos_print_find_row(const char **var_names, logos_term *vals,
                          int n_vars, double conf) {
    FILE *out = logos_query_to_stderr ? stderr : stdout;
    int i;
    for (i = 0; i < n_vars; i++) {
        if (i > 0) fprintf(out, ", ");
        fprintf(out, "%s=", var_names[i]);
        logos_print_term(vals[i]);
    }
    fprintf(out, "  [confidence: %.3f]\n", conf);
}
