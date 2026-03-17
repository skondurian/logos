#ifndef LOGOS_PRIMITIVES_H
#define LOGOS_PRIMITIVES_H

/*
 * Logos built-in primitive predicates.
 *
 * Each function returns 1 on success (with output variables bound via
 * logos_unify), 0 on failure.  These are called inline in compiled rule bodies;
 * the enclosing rule dispatcher handles mark/undo for backtracking.
 */

#include "logos_runtime.h"

/* ── Equality / truth ───────────────────────────────────────────────────── */
int logos_prim_equal(logos_env *env, logos_term a, logos_term b);
int logos_prim_true(logos_env *env);

/* ── List primitives ────────────────────────────────────────────────────── */
/* list-cons(H, T, L) : L = [H|T]  (bi-directional via unify) */
int logos_prim_list_cons(logos_env *env, logos_term h, logos_term t,
                         logos_term l);
/* list-empty(L)  : L is [] */
int logos_prim_list_empty(logos_env *env, logos_term l);
/* list-head(H, L): H = head of L */
int logos_prim_list_head(logos_env *env, logos_term h, logos_term l);
/* list-tail(T, L): T = tail of L */
int logos_prim_list_tail(logos_env *env, logos_term t, logos_term l);
/* list-length(L, N): N = length of L */
int logos_prim_list_length(logos_env *env, logos_term l, logos_term n);
/* list-nth(L, N, X): X = L[N]  (0-based) */
int logos_prim_list_nth(logos_env *env, logos_term l, logos_term n,
                        logos_term x);
/* list-append(L1, L2, L3): L3 = L1 ++ L2 */
int logos_prim_list_append(logos_env *env, logos_term l1, logos_term l2,
                           logos_term l3);
/* list-reverse(L, R): R = reverse of L */
int logos_prim_list_reverse(logos_env *env, logos_term l, logos_term r);
/* list-flatten(L, F): F = flattened L */
int logos_prim_list_flatten(logos_env *env, logos_term l, logos_term f);

/* ── Numeric primitives ─────────────────────────────────────────────────── */
int logos_prim_num_add(logos_env *env, logos_term a, logos_term b,
                       logos_term c);
int logos_prim_num_sub(logos_env *env, logos_term a, logos_term b,
                       logos_term c);
int logos_prim_num_mul(logos_env *env, logos_term a, logos_term b,
                       logos_term c);
int logos_prim_num_div(logos_env *env, logos_term a, logos_term b,
                       logos_term c);
int logos_prim_num_mod(logos_env *env, logos_term a, logos_term b,
                       logos_term c);
int logos_prim_num_abs(logos_env *env, logos_term a, logos_term b);
int logos_prim_num_floor(logos_env *env, logos_term a, logos_term b);
int logos_prim_num_ceil(logos_env *env, logos_term a, logos_term b);
int logos_prim_num_min(logos_env *env, logos_term a, logos_term b,
                       logos_term c);
int logos_prim_num_max(logos_env *env, logos_term a, logos_term b,
                       logos_term c);

/* ── Type-check primitives ──────────────────────────────────────────────── */
int logos_prim_is_string(logos_env *env, logos_term t);
int logos_prim_is_number(logos_env *env, logos_term t);
int logos_prim_is_list(logos_env *env, logos_term t);
int logos_prim_ground(logos_env *env, logos_term t);

/* ── String primitives ──────────────────────────────────────────────────── */
int logos_prim_str_concat(logos_env *env, logos_term a, logos_term b,
                          logos_term c);
int logos_prim_str_length(logos_env *env, logos_term s, logos_term n);
int logos_prim_str_char_at(logos_env *env, logos_term s, logos_term idx,
                           logos_term ch);
int logos_prim_str_starts_with(logos_env *env, logos_term s, logos_term prefix);
int logos_prim_str_ends_with(logos_env *env, logos_term s, logos_term suffix);
int logos_prim_str_slice(logos_env *env, logos_term s, logos_term start,
                         logos_term end, logos_term result);
int logos_prim_str_to_number(logos_env *env, logos_term s, logos_term n);
int logos_prim_number_to_str(logos_env *env, logos_term n, logos_term s);
int logos_prim_str_split(logos_env *env, logos_term s, logos_term sep,
                         logos_term lst);
int logos_prim_str_join(logos_env *env, logos_term lst, logos_term sep,
                        logos_term result);
int logos_prim_str_upper(logos_env *env, logos_term s, logos_term u);
int logos_prim_str_lower(logos_env *env, logos_term s, logos_term l);
int logos_prim_str_trim(logos_env *env, logos_term s, logos_term t);
int logos_prim_str_contains(logos_env *env, logos_term s, logos_term sub);

/* ── Character class predicates ─────────────────────────────────────────── */
int logos_prim_char_alpha(logos_env *env, logos_term c);
int logos_prim_char_digit(logos_env *env, logos_term c);
int logos_prim_char_whitespace(logos_env *env, logos_term c);
int logos_prim_char_alnum(logos_env *env, logos_term c);
int logos_prim_char_code(logos_env *env, logos_term c, logos_term n);

#endif /* LOGOS_PRIMITIVES_H */
