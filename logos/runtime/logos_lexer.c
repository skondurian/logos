/*
 * logos_lexer.c — C implementation of the Logos tokenizer.
 *
 * Mirrors logos/lexer.py exactly:
 *   - Indentation-sensitive: INDENT/DEDENT injected per block
 *   - Identifiers include hyphens: [A-Za-z][A-Za-z0-9_-]*
 *   - Uppercase-first identifiers become VARIABLE tokens
 *   - Keywords and duration units classified post-scan
 *   - Numbers may have optional leading '-'
 *   - Output: cons-list of [type, value] pairs (strings)
 */

#include "logos_lexer.h"
#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include <stdio.h>

/* ── Keyword / duration-unit tables ─────────────────────────────────────── */

static const char *KEYWORDS[] = {
    "if","where","find","query","import","from","not","retract",
    "context","transform","within","true","false","True","False",
    "absolute","zero","low","medium","high","fallback","confidence",
    "provenance","considering","maximize","minimize","require","intent",
    "confidence-threshold","error-tolerance","extends","of","and","or",
    NULL
};

static const char *DURATION_UNITS[] = {
    "years","year","months","month","days","day",
    "hours","hour","minutes","minute","seconds","second",
    NULL
};

static int str_in_table(const char *word, const char **table) {
    for (int i = 0; table[i]; i++)
        if (strcmp(word, table[i]) == 0) return 1;
    return 0;
}

/* ── Raw token accumulator ───────────────────────────────────────────────── */

#define LEXER_MAX_TOKENS 65536
#define LEXER_TMP_SIZE   8192

typedef struct { const char *type; const char *value; } raw_tok_t;

typedef struct {
    raw_tok_t toks[LEXER_MAX_TOKENS];
    int count;
} tok_buf_t;

static void tok_push(tok_buf_t *b, const char *type, const char *value) {
    if (b->count >= LEXER_MAX_TOKENS) return;
    b->toks[b->count].type  = logos_intern(type);
    b->toks[b->count].value = logos_intern(value);
    b->count++;
}

/* ── Tokenize one stripped line (no leading whitespace) ─────────────────── */

static void scan_line(tok_buf_t *b, const char *p, int len) {
    char tmp[LEXER_TMP_SIZE];
    int  i = 0;

    while (i < len) {
        unsigned char c = (unsigned char)p[i];

        /* Skip intra-line whitespace */
        if (c == ' ' || c == '\t') { i++; continue; }

        /* Comment: // … rest of line */
        if (c == '/' && i+1 < len && (unsigned char)p[i+1] == '/') break;

        /* String literal: "…" with backslash escapes */
        if (c == '"') {
            int start = i++;
            while (i < len) {
                if ((unsigned char)p[i] == '\\' && i+1 < len) { i += 2; continue; }
                if ((unsigned char)p[i] == '"')                { i++;    break;  }
                i++;
            }
            int sz = i - start;
            if (sz >= LEXER_TMP_SIZE) sz = LEXER_TMP_SIZE - 1;
            memcpy(tmp, p + start, sz);
            tmp[sz] = '\0';
            tok_push(b, "STRING", tmp);
            continue;
        }

        /* UTF-8 arrow → (0xE2 0x86 0x92) */
        if (c == 0xE2 && i+2 < len &&
            (unsigned char)p[i+1] == 0x86 && (unsigned char)p[i+2] == 0x92) {
            tok_push(b, "ARROW", "\xe2\x86\x92"); i += 3; continue;
        }

        /* Arrow -> */
        if (c == '-' && i+1 < len && (unsigned char)p[i+1] == '>') {
            tok_push(b, "ARROW", "->"); i += 2; continue;
        }

        /* Number: -?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)? */
        if (isdigit(c) ||
            (c == '-' && i+1 < len && isdigit((unsigned char)p[i+1]))) {
            int start = i;
            if (c == '-') i++;
            while (i < len && isdigit((unsigned char)p[i])) i++;
            if (i < len && p[i] == '.') {
                i++;
                while (i < len && isdigit((unsigned char)p[i])) i++;
            }
            if (i < len && (p[i] == 'e' || p[i] == 'E')) {
                i++;
                if (i < len && (p[i] == '+' || p[i] == '-')) i++;
                while (i < len && isdigit((unsigned char)p[i])) i++;
            }
            int sz = i - start;
            if (sz >= LEXER_TMP_SIZE) sz = LEXER_TMP_SIZE - 1;
            memcpy(tmp, p + start, sz);
            tmp[sz] = '\0';
            tok_push(b, "NUMBER", tmp);
            continue;
        }

        /* Multi-char operators (must precede single-char) */
        if (c == ':' && i+1 < len && p[i+1] == '=') { tok_push(b,"ASSIGN", ":="); i+=2; continue; }
        if (c == '>' && i+1 < len && p[i+1] == '=') { tok_push(b,"OP_GEQ", ">="); i+=2; continue; }
        if (c == '<' && i+1 < len && p[i+1] == '=') { tok_push(b,"OP_LEQ", "<="); i+=2; continue; }
        if (c == '!' && i+1 < len && p[i+1] == '=') { tok_push(b,"OP_NEQ", "!="); i+=2; continue; }

        /* Single-char operators / punctuation */
        switch (c) {
            case '>': tok_push(b,"OP_GT",    ">"); i++; continue;
            case '<': tok_push(b,"OP_LT",    "<"); i++; continue;
            case '=': tok_push(b,"OP_EQ",    "="); i++; continue;
            case '+': tok_push(b,"OP_PLUS",  "+"); i++; continue;
            case '-': tok_push(b,"OP_MINUS", "-"); i++; continue;
            case '*': tok_push(b,"OP_STAR",  "*"); i++; continue;
            case '/': tok_push(b,"OP_SLASH", "/"); i++; continue;
            case '|': tok_push(b,"PIPE",     "|"); i++; continue;
            case ':': tok_push(b,"COLON",    ":"); i++; continue;
            case ',': tok_push(b,"COMMA",    ","); i++; continue;
            case '.': tok_push(b,"DOT",      "."); i++; continue;
            case '(': tok_push(b,"LPAREN",   "("); i++; continue;
            case ')': tok_push(b,"RPAREN",   ")"); i++; continue;
            case '{': tok_push(b,"LBRACE",   "{"); i++; continue;
            case '}': tok_push(b,"RBRACE",   "}"); i++; continue;
            case '[': tok_push(b,"LBRACKET", "["); i++; continue;
            case ']': tok_push(b,"RBRACKET", "]"); i++; continue;
            case '?': tok_push(b,"QUESTION", "?"); i++; continue;
        }

        /* Identifier: [A-Za-z][A-Za-z0-9_-]* (hyphens allowed) */
        if (isalpha(c)) {
            int start = i++;
            while (i < len &&
                   (isalnum((unsigned char)p[i]) ||
                    p[i] == '_' || p[i] == '-'))
                i++;
            int sz = i - start;
            if (sz >= LEXER_TMP_SIZE) sz = LEXER_TMP_SIZE - 1;
            memcpy(tmp, p + start, sz);
            tmp[sz] = '\0';
            if (str_in_table(tmp, DURATION_UNITS))
                tok_push(b, "DURATION_UNIT", tmp);
            else if (str_in_table(tmp, KEYWORDS))
                tok_push(b, "KEYWORD", tmp);
            else if (isupper((unsigned char)tmp[0]))
                tok_push(b, "VARIABLE", tmp);
            else
                tok_push(b, "IDENTIFIER", tmp);
            continue;
        }

        i++; /* skip unrecognised byte */
    }
}

/* ── Full tokenizer with INDENT/DEDENT injection ─────────────────────────── */

static tok_buf_t *logos_tokenize_str(const char *source) {
    tok_buf_t *b = calloc(1, sizeof(tok_buf_t));

    int indent_stack[256];
    int indent_top = 0;
    indent_stack[0] = 0;

    const char *src = source;
    int src_len = (int)strlen(source);
    int pos = 0;

    while (pos < src_len) {
        /* Find end of current line */
        int line_start = pos;
        while (pos < src_len && src[pos] != '\n') pos++;
        int line_end = pos;
        if (pos < src_len) pos++; /* skip '\n' */

        const char *line = src + line_start;
        int line_len = line_end - line_start;

        /* Count leading whitespace (tab = 4 spaces) */
        int ws = 0, k = 0;
        while (k < line_len && (line[k] == ' ' || line[k] == '\t')) {
            ws += (line[k] == '\t') ? 4 : 1;
            k++;
        }
        const char *stripped = line + k;
        int stripped_len = line_len - k;

        /* Skip blank lines and comment-only lines */
        if (stripped_len == 0) continue;
        if (stripped_len >= 2 &&
            stripped[0] == '/' && stripped[1] == '/') continue;

        /* INDENT / DEDENT */
        int current = indent_stack[indent_top];
        if (ws > current) {
            if (indent_top < 254) indent_stack[++indent_top] = ws;
            tok_push(b, "INDENT", "");
        } else if (ws < current) {
            while (indent_top > 0 && indent_stack[indent_top] > ws) {
                indent_top--;
                tok_push(b, "DEDENT", "");
            }
        }

        /* Tokenize stripped line contents */
        scan_line(b, stripped, stripped_len);
        tok_push(b, "NEWLINE", "\n");
    }

    /* Close any remaining open indents */
    while (indent_top > 0) {
        indent_top--;
        tok_push(b, "DEDENT", "");
    }
    tok_push(b, "EOF", "");

    return b;
}

/* ── Convert token buffer → Logos cons-list of [type, value] pairs ──────── */

static logos_term tok_buf_to_logos_list(logos_env *env, tok_buf_t *b) {
    logos_term result = logos_nil();
    /* Build in reverse so that cons gives the correct head-to-tail order */
    for (int i = b->count - 1; i >= 0; i--) {
        logos_term type_t  = logos_string(b->toks[i].type);
        logos_term value_t = logos_string(b->toks[i].value);
        logos_term pair    = logos_list_cons(type_t,
                                logos_list_cons(value_t, logos_nil()));
        result = logos_list_cons(pair, result);
    }
    return result;
}

/* ── Public primitives ───────────────────────────────────────────────────── */

int logos_prim_lex_file(logos_env *env,
                        logos_term path, logos_term tokens_out) {
    extern int _cons_slab_count;
    path = logos_walk(env, path);
    if (path.tag != LOGOS_STRING) return 0;
    fprintf(stderr, "[logos-debug] lex-file: %s (slabs so far: %d)\n", path.s, _cons_slab_count);

    FILE *f = fopen(path.s, "r");
    if (!f) return 0;

    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *source = malloc((size_t)sz + 1);
    if (!source) { fclose(f); return 0; }
    fread(source, 1, (size_t)sz, f);
    fclose(f);
    source[sz] = '\0';

    tok_buf_t *b = logos_tokenize_str(source);
    free(source);

    logos_term tok_list = tok_buf_to_logos_list(env, b);
    free(b);

    return logos_unify(env, tokens_out, tok_list);
}

int logos_prim_lex_source(logos_env *env,
                          logos_term source, logos_term tokens_out) {
    source = logos_walk(env, source);
    if (source.tag != LOGOS_STRING) return 0;

    tok_buf_t *b = logos_tokenize_str(source.s);
    logos_term tok_list = tok_buf_to_logos_list(env, b);
    free(b);

    return logos_unify(env, tokens_out, tok_list);
}
