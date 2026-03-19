# Logos Standard Library

The standard library is written in Logos itself and lives in `logos/stdlib/`.
Import with `import * from "stdlib/<module>"`.

---

## 1. lists

**Import:** `import * from "stdlib/lists"`

| Predicate | Description |
|---|---|
| `list-member(X, L)` | X is an element of L (backtrackable — yields each member) |
| `list-last(X, L)` | X is the last element of L |
| `list-prefix(P, L)` | P is a prefix of L |
| `list-suffix(S, L)` | S is a suffix of L |
| `list-zip-elem(A, B, [A, B])` | Pair two elements into a two-element list |
| `list-sum(L, S)` | S is the sum of all elements in L |
| `list-max(L, M)` | M is the maximum element of L |
| `list-min(L, M)` | M is the minimum element of L |

---

## 2. strings

**Import:** `import * from "stdlib/strings"`

| Predicate | Description |
|---|---|
| `str-empty(S)` | S is the empty string |
| `str-non-empty(S)` | S is non-empty |
| `str-numeric(S)` | S can be parsed as a number |
| `str-concat3(A, B, C, R)` | R = A ++ B ++ C |
| `str-concat4(A, B, C, D, R)` | R = A ++ B ++ C ++ D |
| `str-prefix(P, S)` | S starts with P (alias for `str-starts-with`) |
| `str-suffix(Suf, S)` | S ends with Suf (alias for `str-ends-with`) |
| `str-chars(S, Chars)` | Chars = list of single-character strings making up S |
| `str-char-member(C, S)` | C is a character in string S |

---

## 3. math

**Import:** `import * from "stdlib/math"`

| Predicate | Description |
|---|---|
| `positive(X)` | X > 0 |
| `negative(X)` | X < 0 |
| `non-negative(X)` | X >= 0 |
| `zero(X)` | X = 0 |
| `even(X)` | X mod 2 = 0 |
| `odd(X)` | X mod 2 = 1 |
| `between(Lo, Hi, X)` | Lo <= X <= Hi |
| `clamp(X, Lo, Hi, R)` | R = max(Lo, min(Hi, X)) |
| `square(X, Y)` | Y = X × X |
| `increment(X, Y)` | Y = X + 1 |
| `decrement(X, Y)` | Y = X − 1 |

---

## 4. io

**Import:** `import * from "stdlib/io"`

| Predicate | Description |
|---|---|
| `print(X)` | Write X as string to stdout with newline |
| `print-list(L)` | Write each element of L on its own line |

---

## Usage Example

```logos
import * from "stdlib/lists"
import * from "stdlib/math"

ages([30, 25, 42, 17])

adult-count(N) if:
  ages(AgeList)
  list-member(Age, AgeList)
  positive(Age)
  Age >= 18
```
