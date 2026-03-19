# Logos Built-in Primitives

Primitives are predicates implemented natively (in Python or C). They are
available in any Logos program without import. All predicates use unification:
output arguments are unified with computed results.

---

## 1. Equality & Truth

| Predicate | Description |
|---|---|
| `equal(A, B)` | Succeeds if A and B unify |
| `true()` | Always succeeds |
| `is-string(X)` | X is a string value |
| `is-number(X)` | X is a numeric value |
| `is-list(X)` | X is a list |
| `ground(X)` | X contains no unbound variables |

---

## 2. Numeric Primitives

| Predicate | Description |
|---|---|
| `num-add(A, B, C)` | C = A + B |
| `num-sub(A, B, C)` | C = A − B |
| `num-mul(A, B, C)` | C = A × B |
| `num-div(A, B, C)` | C = A / B |
| `num-mod(A, B, C)` | C = A mod B |
| `num-abs(A, B)` | B = \|A\| |
| `num-floor(A, B)` | B = ⌊A⌋ |
| `num-ceil(A, B)` | B = ⌈A⌉ |
| `num-min(A, B, C)` | C = min(A, B) |
| `num-max(A, B, C)` | C = max(A, B) |
| `number-to-str(N, S)` | S = string representation of N |
| `number-to-float-str(N, S)` | S = float string (e.g. "3.0") |

---

## 3. String Primitives

| Predicate | Description |
|---|---|
| `str-concat(A, B, C)` | C = A ++ B |
| `str-length(S, N)` | N = length of S |
| `str-char-at(S, I, C)` | C = character at index I of S |
| `str-starts-with(S, Prefix)` | S starts with Prefix |
| `str-ends-with(S, Suffix)` | S ends with Suffix |
| `str-slice(S, Start, End, T)` | T = S[Start:End] |
| `str-to-number(S, N)` | N = numeric value of S |
| `str-split(S, Sep, Parts)` | Parts = S split on Sep |
| `str-join(Parts, Sep, S)` | S = Parts joined with Sep |
| `str-upper(S, T)` | T = uppercase S |
| `str-lower(S, T)` | T = lowercase S |
| `str-trim(S, T)` | T = S with leading/trailing whitespace removed |
| `str-contains(S, Sub)` | S contains substring Sub |
| `str-unescape(S, T)` | T = S with escape sequences interpreted |

---

## 4. Character Primitives

| Predicate | Description |
|---|---|
| `char-alpha(C)` | C is an alphabetic character |
| `char-digit(C)` | C is a decimal digit character |
| `char-whitespace(C)` | C is a whitespace character |
| `char-alnum(C)` | C is alphanumeric |
| `char-code(C, N)` | N = ASCII code of character C |

---

## 5. List Primitives

| Predicate | Description |
|---|---|
| `list-cons(H, T, L)` | L = [H \| T] |
| `list-empty(L)` | L is the empty list `[]` |
| `list-head(L, H)` | H = first element of L |
| `list-tail(L, T)` | T = L with first element removed |
| `list-length(L, N)` | N = length of L |
| `list-nth(L, I, X)` | X = L[I] (0-indexed) |
| `list-append(A, B, C)` | C = A ++ B |
| `list-reverse(L, R)` | R = reverse of L |
| `list-flatten(L, F)` | F = L with nested lists flattened one level |

---

## 6. I/O Primitives

| Predicate | Description |
|---|---|
| `write-output(S)` | Write string S to stdout |
| `write-line(S)` | Write S to stdout followed by newline |
| `write-stderr(S)` | Write S to stderr |
| `read-file(Path, Content)` | Content = file contents as string |

---

## 7. Fact Store Primitives

| Predicate | Description |
|---|---|
| `assert-fact(Subject, Predicate, Value)` | Assert a new fact at runtime |

`assert-fact` modifies the live fact store. In compiled binaries, this asserts
into the `logos_graph` and is visible to subsequent queries.

---

## 8. System Primitives

| Predicate | Description |
|---|---|
| `argv(I, Value)` | Value = command-line argument at index I |
| `argc(N)` | N = number of command-line arguments |
| `lex-file(Path, Tokens)` | Tokens = tokenized .logos file (used by self-hosted compiler) |

---

## 9. Meta-Interpreter Primitives

These are used internally by `interpreter.logos` and `evaluator.logos` to
implement the self-hosted execution engine.

| Predicate | Description |
|---|---|
| `register-rule-ast(Name, Args, Conditions)` | Register a rule from AST at runtime |
| `exec-bool-query-ast(PredicateAST)` | Execute a boolean query from AST |
| `exec-find-query-ast(QueryAST)` | Execute a find query from AST |

AST format matches the output of `parser.logos` (tagged lists).
