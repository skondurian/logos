#ifndef LOGOS_META_H
#define LOGOS_META_H

/*
 * logos_meta.h — Runtime meta-interpreter for Logos.
 *
 * Provides three primitives used by the self-hosted Logos evaluator:
 *   register-rule-ast(Name, Args, Conditions)
 *   exec-bool-query-ast(Name, QueryArgs)
 *   exec-find-query-ast(VarNames, Conditions)
 *
 * Rules are stored as cons-list ASTs in a global table.  At query time the
 * meta-interpreter walks those ASTs, resolves variable names to logos VAR
 * terms, evaluates conditions, and prints results.
 *
 * AST format (matches logos/parser.logos):
 *   condition : ["call",     Name, Args]
 *             | ["not-call", Name, Args]
 *             | ["cmp",      Left, Op, Right]
 *   value     : string | number
 *             | ["var",      Name]        — Logos variable
 *             | ["id",       Name]        — atom / identifier
 *             | ["path",     Subj, Pred]  — graph-path lookup
 *             | ["path-var", VarAst, Pred]
 */

#include "logos_runtime.h"
#include "logos_primitives.h"

/* ── Public primitives ─────────────────────────────────────────────────────── */

/* register-rule-ast(Name, Args, Conditions) — store rule in dynamic table */
int logos_prim_register_rule_ast(logos_env *env, logos_term name,
                                  logos_term args, logos_term conds);

/* exec-bool-query-ast(Name, QueryArgs) — try all matching rules, print result */
int logos_prim_exec_bool_query_ast(logos_env *env, logos_term name,
                                    logos_term query_args);

/* exec-find-query-ast(VarNames, Conditions) — evaluate conditions, print row */
int logos_prim_exec_find_query_ast(logos_env *env, logos_term var_names,
                                    logos_term conds);

#endif /* LOGOS_META_H */
