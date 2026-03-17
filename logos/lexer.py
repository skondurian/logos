"""
Lexer for Logos — handles indentation-sensitive tokenization.

Rather than using Lark's built-in indentation handling (which has edge cases),
we pre-process the raw source into a token stream with synthetic INDENT/DEDENT
tokens, then feed that to the Lark parser.

Token types produced (subset):
  IDENTIFIER, VARIABLE, NUMBER, STRING
  DURATION_UNIT, KEYWORD, OPERATOR, PUNCTUATION
  INDENT, DEDENT, NEWLINE
  COMMENT (filtered out before parsing)
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Iterator


# ─── Token ────────────────────────────────────────────────────────────────────

@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.value!r}, {self.line}:{self.col})"


# ─── Keyword set ──────────────────────────────────────────────────────────────

KEYWORDS = {
    "if", "where", "find", "query", "import", "from", "not",
    "retract", "context", "transform", "within",
    "true", "false", "True", "False",
    "absolute", "zero", "low", "medium", "high",
    "fallback", "confidence", "provenance",
    "considering", "maximize", "minimize", "require", "intent",
    "confidence-threshold", "error-tolerance", "extends",
    "of", "and", "or",
}

DURATION_UNITS = {
    "years", "year", "months", "month", "days", "day",
    "hours", "hour", "minutes", "minute", "seconds", "second",
}


# ─── Regex patterns ───────────────────────────────────────────────────────────

TOKEN_PATTERNS: list[tuple[str, str]] = [
    ("COMMENT",    r"//[^\n]*"),
    ("NUMBER",     r"-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"),
    ("STRING",     r'"[^"\\]*"'),
    ("ARROW",      r"→|->"),
    ("ASSIGN",     r":="),
    # Multi-char operators MUST come before single-char ones
    ("OP_GEQ",     r">="),
    ("OP_LEQ",     r"<="),
    ("OP_NEQ",     r"!="),
    ("OP_GT",      r">"),
    ("OP_LT",      r"<"),
    ("OP_EQ",      r"="),
    ("OP_PLUS",    r"\+"),
    ("OP_MINUS",   r"-"),
    ("OP_STAR",    r"\*"),
    ("OP_SLASH",   r"/"),
    ("PIPE",       r"\|"),
    ("COLON",      r":"),
    ("COMMA",      r","),
    ("DOT",        r"\."),
    ("LPAREN",     r"\("),
    ("RPAREN",     r"\)"),
    ("LBRACE",     r"\{"),
    ("RBRACE",     r"\}"),
    ("LBRACKET",   r"\["),
    ("RBRACKET",   r"\]"),
    ("QUESTION",   r"\?"),
    ("NEWLINE",    r"\n"),
    ("WHITESPACE", r"[ \t]+"),
    ("IDENTIFIER", r"[A-Za-z][A-Za-z0-9_-]*"),
]

MASTER_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_PATTERNS)
)


# ─── Tokenizer ────────────────────────────────────────────────────────────────

def tokenize_raw(source: str) -> Iterator[Token]:
    """
    Yield raw tokens (without INDENT/DEDENT handling).
    COMMENT and WHITESPACE tokens are emitted but can be filtered downstream.
    """
    line = 1
    line_start = 0
    for m in MASTER_RE.finditer(source):
        kind = m.lastgroup
        value = m.group()
        col = m.start() - line_start + 1
        if kind == "NEWLINE":
            yield Token("NEWLINE", value, line, col)
            line += 1
            line_start = m.end()
        elif kind == "WHITESPACE":
            pass  # suppress inter-token whitespace (but not leading)
        elif kind == "IDENTIFIER":
            if value in DURATION_UNITS:
                yield Token("DURATION_UNIT", value, line, col)
            elif value in KEYWORDS:
                yield Token("KEYWORD", value, line, col)
            elif value[0].isupper():
                yield Token("VARIABLE", value, line, col)
            else:
                yield Token("IDENTIFIER", value, line, col)
        elif kind == "COMMENT":
            yield Token("COMMENT", value, line, col)
        else:
            yield Token(kind, value, line, col)


def tokenize(source: str) -> list[Token]:
    """
    Full tokenization with INDENT/DEDENT injection and comment stripping.

    Indentation rules:
      - Indent level is determined by leading spaces/tabs on each line.
      - Increasing indent → INDENT token before first token of new block.
      - Decreasing indent → one DEDENT per level closed.
      - Tabs count as 4 spaces.
    """
    lines = source.split("\n")
    tokens: list[Token] = []
    indent_stack = [0]
    line_no = 1

    for raw_line in lines:
        # Count leading whitespace
        stripped = raw_line.lstrip(" \t")
        if not stripped or stripped.startswith("//"):
            line_no += 1
            continue

        indent = len(raw_line) - len(stripped)
        # Normalise tabs → 4 spaces
        indent += raw_line[:len(raw_line) - len(stripped)].count("\t") * 3

        current = indent_stack[-1]
        if indent > current:
            indent_stack.append(indent)
            tokens.append(Token("INDENT", "", line_no, 1))
        elif indent < current:
            while indent_stack and indent_stack[-1] > indent:
                indent_stack.pop()
                tokens.append(Token("DEDENT", "", line_no, 1))

        # Tokenize this line
        line_tokens = [
            t for t in tokenize_raw(stripped)
            if t.type not in ("COMMENT", "NEWLINE", "WHITESPACE")
        ]
        for t in line_tokens:
            t.line = line_no
        tokens.extend(line_tokens)
        tokens.append(Token("NEWLINE", "\n", line_no, len(raw_line) + 1))
        line_no += 1

    # Close any remaining indents
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", "", line_no, 1))

    tokens.append(Token("EOF", "", line_no, 1))
    return tokens
