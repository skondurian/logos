#ifndef LOGOS_RUNTIME_H
#define LOGOS_RUNTIME_H

#include <stddef.h>

/* ── Term tags ──────────────────────────────────────────────────────────────── */
#define LOGOS_INT      0
#define LOGOS_FLOAT    1
#define LOGOS_STRING   2
#define LOGOS_BOOL     3
#define LOGOS_DURATION 4
#define LOGOS_VAR      5
#define LOGOS_NONE     6
#define LOGOS_LIST     7   /* cons cell — .cons points to logos_cons */
#define LOGOS_NIL      8   /* empty list */

/* ── Capacity constants ─────────────────────────────────────────────────────── */
#define LOGOS_MAX_VARS  32768
#define LOGOS_MAX_TRAIL 262144
#define LOGOS_MAX_FACTS 4096
#define LOGOS_MAX_CONS  2097152  /* legacy constant — slab allocator no longer bounded */

/* ── Forward declaration (logos_term ↔ logos_cons mutual recursion) ─────────── */
struct logos_cons;

/* ── Term ───────────────────────────────────────────────────────────────────── */
typedef struct {
    int tag;
    union {
        long              i;       /* LOGOS_INT, LOGOS_BOOL */
        double            f;       /* LOGOS_FLOAT, LOGOS_DURATION */
        const char       *s;       /* LOGOS_STRING (interned pointer) */
        int               var_id;  /* LOGOS_VAR */
        struct logos_cons *cons;   /* LOGOS_LIST */
    };
} logos_term;

/* ── Cons cell (heap-allocated from global pool, never freed) ───────────────── */
typedef struct logos_cons {
    logos_term head;
    logos_term tail;   /* LOGOS_LIST or LOGOS_NIL */
} logos_cons;

/* ── Bindings (dynamically grown heap array) ─────────────────────────────────── */
typedef struct {
    logos_term *bindings;  /* heap-allocated; grows on demand               */
    int         num_vars;  /* logical count of allocated variables           */
    int         capacity;  /* current allocated size of bindings[]           */
} logos_bindings;

/* ── Trail (dynamically grown heap array) ────────────────────────────────────── */
typedef struct {
    int *entries;   /* heap-allocated; grows on demand */
    int  top;
    int  capacity;
} logos_trail;

typedef struct { int trail_top; int num_vars; void *cont_ctx; } logos_mark_t;

/* ── Fact ───────────────────────────────────────────────────────────────────── */
typedef struct {
    const char *subject;
    const char *predicate;
    logos_term  value;
    double      confidence;
} logos_fact;

/* ── Graph ──────────────────────────────────────────────────────────────────── */
typedef struct {
    logos_fact facts[LOGOS_MAX_FACTS];
    int        count;
} logos_graph;

/* ── Environment ────────────────────────────────────────────────────────────── */
struct logos_env;
typedef int (*logos_cont)(struct logos_env *env);

typedef struct logos_env {
    logos_bindings bindings;
    logos_trail    trail;
    logos_graph   *graph;
    double         confidence;    /* accumulated per proof path */
    void          *capture_found; /* int*    — set to 1 on any success */
    void          *capture_conf;  /* double* — accumulates via logos_disjoin */
    void          *cont_ctx;      /* current CPS continuation context */
} logos_env;

/* ── Scan callback ──────────────────────────────────────────────────────────── */
typedef int (*logos_scan_cb)(logos_env *env, const char *subj,
                              logos_term val, double conf, logos_cont k);

/* ── Environment init/teardown ──────────────────────────────────────────────── */
void logos_env_init(logos_env *env);   /* initialize dynamic pools             */
void logos_env_free(logos_env *env);   /* release dynamic pools                */

/* ── Backtracking ───────────────────────────────────────────────────────────── */
logos_mark_t logos_mark(logos_env *env);
void         logos_undo(logos_env *env, logos_mark_t mark);

/* ── Variables ──────────────────────────────────────────────────────────────── */
logos_term   logos_alloc_var(logos_env *env);
logos_term   logos_walk(logos_env *env, logos_term t);
int          logos_unify(logos_env *env, logos_term a, logos_term b);

/* ── Graph ──────────────────────────────────────────────────────────────────── */
void logos_graph_assert(logos_graph *g, const char *subj, const char *pred,
                        logos_term val, double conf);
int  logos_graph_lookup(logos_graph *g, const char *subj, const char *pred,
                        logos_term *out, double *conf_out);
int  logos_graph_scan(logos_graph *g, const char *pred, logos_env *env,
                      logos_scan_cb cb, logos_cont k);

/* ── Confidence arithmetic ──────────────────────────────────────────────────── */
double logos_conjoin(double a, double b);   /* a * b                    */
double logos_disjoin(double a, double b);   /* 1 - (1-a)(1-b)           */
double logos_degrade(double c);             /* c * 0.95                 */

/* ── Comparison  op: 0=>=  1=<=  2=>  3=<  4==  5=!= ──────────────────────── */
int logos_compare(logos_term l, int op, logos_term r);

/* ── Scalar term constructors ───────────────────────────────────────────────── */
logos_term   logos_int(long i);
logos_term   logos_float(double f);
logos_term   logos_string(const char *s);    /* interns the string */
logos_term   logos_duration(double secs);    /* LOGOS_DURATION, .f = seconds */
const char  *logos_intern(const char *s);

/* ── List constructors (global pool — no env needed) ────────────────────────── */
logos_term   logos_nil(void);
logos_cons  *logos_alloc_cons(void);
logos_term   logos_list_cons(logos_term head, logos_term tail);
logos_term   logos_list_from_array(logos_term *terms, int n);
int          logos_is_nil(logos_term t);
int          logos_is_list(logos_term t);

/* ── Built-in continuations ─────────────────────────────────────────────────── */
int k_bool_capture(logos_env *env);  /* accumulates confidence, returns 0 */
int k_naf_capture(logos_env *env);   /* sets found=1, returns 0           */

/* ── Output ─────────────────────────────────────────────────────────────────── */
extern int logos_query_to_stderr;  /* set to 1 to redirect query output to stderr */
void logos_print_term(logos_term t);
void logos_print_bool_result(const char *text, int found, double conf);
void logos_print_find_row(const char **var_names, logos_term *vals,
                          int n_vars, double conf);

#endif /* LOGOS_RUNTIME_H */
