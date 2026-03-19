#ifndef LOGOS_LEXER_H
#define LOGOS_LEXER_H

/*
 * logos_lexer.h — C implementation of the Logos tokenizer.
 *
 * Produces the same token stream as logos/lexer.py: INDENT/DEDENT-annotated
 * list of [type, value] pairs as a Logos cons-list.
 *
 * Token types: IDENTIFIER, VARIABLE, NUMBER, STRING, DURATION_UNIT, KEYWORD,
 *   ARROW, ASSIGN, OP_GEQ, OP_LEQ, OP_NEQ, OP_GT, OP_LT, OP_EQ, OP_PLUS,
 *   OP_MINUS, OP_STAR, OP_SLASH, PIPE, COLON, COMMA, DOT, LPAREN, RPAREN,
 *   LBRACE, RBRACE, LBRACKET, RBRACKET, QUESTION, INDENT, DEDENT, NEWLINE, EOF
 */

#include "logos_runtime.h"

/* lex-file(Path, Tokens) — read file, tokenize, unify result with Tokens */
int logos_prim_lex_file(logos_env *env, logos_term path,
                        logos_term tokens_out);

/* lex-source(Source, Tokens) — tokenize a string, unify result with Tokens */
int logos_prim_lex_source(logos_env *env, logos_term source,
                          logos_term tokens_out);

#endif /* LOGOS_LEXER_H */
