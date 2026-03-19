# Logos Language Reference

Logos is a probabilistic logic programming language. Programs consist of facts,
inference rules, and queries. Execution is backward-chaining SLD resolution with
confidence propagation.

---

## 1. Syntax Overview

Logos is indentation-sensitive. Blocks are delimited by INDENT/DEDENT (tabs = 4
spaces). Comments begin with `//` and extend to end of line.

### 1.1 Type Declarations

```logos
Person:
  name: HumanName
  age:  Duration

Animal: (Entity)
  name: HumanName
```

A type declaration names a type, optionally lists parent types in parentheses,
and declares fields with their types. All types implicitly extend `Entity` if
no parent is given.

### 1.2 Semantic Bindings (Facts)

```logos
age of alice := 30 years
  confidence: absolute
  provenance: "birth-record"

citizenship of alice := "US"

score of bob := 0.87
  confidence: [0.80, 0.95]
```

Syntax: `<path> := <value>` optionally followed by an indented annotations block.

**Paths** are written as `attribute of subject` or `subject.attribute`.

**Values:**
- Numbers: `42`, `3.14`, `-7`
- Strings: `"hello"`
- Booleans: `true`, `false`
- Durations: `30 years`, `6 months`, `18 years`
- Lists: `[a, b, c]`
- Sets: `{a, b, c}`
- Arithmetic: `X + 1`, `A * B`

**Annotations (all optional):**

| Annotation | Values | Meaning |
|---|---|---|
| `confidence:` | `absolute`, `0.9`, `[0.8, 0.95]` | Certainty level |
| `provenance:` | `"string"` | Source description |
| `fallback:` | `other.path` | Alternative if primary below threshold |
| `context:` | `ctx-name` | Restrict to named context |

`confidence: absolute` means certainty 1.0 (Dirac distribution).
`confidence: [low, high]` fits a Beta distribution to the 95% confidence interval.

### 1.3 Inference Rules

```logos
can-vote(P) if:
  P.age >= 18 years
  P.citizenship = "US"

eligible(P) if:
  can-vote(P)
  not disqualified(P)
```

A rule head `predicate(args)` is followed by `if:` and an indented list of
conditions. All conditions must hold (conjunction). Variables are uppercase.

**Conditions:**

| Form | Meaning |
|---|---|
| `predicate(args)` | Predicate call (must succeed) |
| `not predicate(args)` | Negation as failure (succeeds iff predicate fails) |
| `P.field >= value` | Path comparison |
| `X >= Y` | Variable comparison |

**Comparison operators:** `>=`, `<=`, `>`, `<`, `=`, `!=`

**Unit rules** (facts as predicates, no conditions):

```logos
dur-unit-secs("years", 31557600.0)
```

### 1.4 Queries

**Boolean query** — does this hold?

```logos
query: can-vote(alice)?
```

Output: `can-vote(alice): true  [confidence: 0.950]` or `can-vote(alice): false`

**Find query** — what values satisfy this?

```logos
find P where can-vote(P)
```

Output: one row per solution with variable bindings and confidence.

### 1.5 Imports

```logos
import * from "stdlib/lists"
import * from "../other-module"
```

Imports are resolved relative to the importing file. The `.logos` extension is
added automatically if absent. Circular imports are detected and rejected.

### 1.6 Context Declarations

```logos
context medical:
  confidence-threshold: 0.9
  error-tolerance: low
  extends: default

context casual:
  confidence-threshold: 0.5
  error-tolerance: medium
```

Contexts partition reasoning by domain. Confidence thresholds filter query
results. Error tolerances: `zero` (0.0), `low` (0.1), `medium` (0.3), `high` (0.7).

---

## 2. Types

### 2.1 Built-in Types

| Type | Description |
|---|---|
| `Entity` | Root of all types |
| `Number` | Any numeric value |
| `Integer` | Whole numbers |
| `Float` | Floating-point numbers |
| `Text` | String values |
| `HumanName` | Human name (subtype of Text) |
| `Boolean` | `true` / `false` |
| `Duration` | Time intervals (stored as seconds) |
| `Timestamp` | Points in time |
| `GeoLocation` | Geographic coordinates |
| `URL` | Web addresses |
| `Set` | Unordered collection |
| `List` | Ordered sequence |
| `Optional` | Nullable wrapper |

### 2.2 Duration Units

| Unit | Seconds |
|---|---|
| `seconds` / `second` | 1 |
| `minutes` / `minute` | 60 |
| `hours` / `hour` | 3600 |
| `days` / `day` | 86400 |
| `weeks` / `week` | 604800 |
| `months` / `month` | 2629800 |
| `years` / `year` | 31557600 |

Duration values are stored as floats (seconds). `30 years` becomes `946728000.0`.

### 2.3 Type Lattice

Types form a multiple-inheritance DAG. `is_subtype_of(A, B)` holds if there
is a path from A to B in the IS-A graph. Fields are inherited from all ancestors.
The least common ancestor (LCA) is used for type inference.

---

## 3. Variables

Variables are identifiers starting with an uppercase letter (`P`, `X`, `Name`).
Variables are **unification variables** — they are bound by unification during
proof search, not by assignment.

- A variable unbound at query time will be matched against all candidate values.
- A variable bound in an earlier condition is substituted in later conditions.
- Variables are scoped to a single rule or query.

**Renaming:** The inference engine renames variables per rule invocation to prevent
scope collisions across recursive calls.

---

## 4. Confidence Arithmetic

Every fact carries a confidence value in [0, 1]. Confidence propagates through
inference:

| Operation | Formula |
|---|---|
| Conjunction (AND) | `P(A ∧ B) = P(A) × P(B)` |
| Disjunction (OR) | `P(A ∨ B) = 1 − (1−P(A))(1−P(B))` |
| Degradation | `P × 0.95` per inference step |

**Multiple proof paths** for the same goal are OR-combined. The confidence
reported for a query is the disjunction of all successful proof paths.

`confidence: absolute` pins confidence to 1.0 with no degradation.

**Fallback chains:** If a fact's confidence is below the active context's
threshold, the `fallback:` annotation specifies an alternative path to try.
The first alternative meeting the threshold wins; otherwise the last fallback
is used at its declared confidence.

---

## 5. Negation as Failure

```logos
not disqualified(P)
```

`not goal` succeeds if and only if `goal` fails (produces no solutions). This
is the closed-world assumption: if a fact cannot be derived, it is assumed false.

NAF does not propagate or reduce confidence.

---

## 6. Path Access

`P.age` looks up the `age` attribute of the value bound to `P` in the semantic
graph. Equivalent syntactic forms:

- `P.age` — dot notation
- `age of P` — "of" notation (in fact values)

In rule conditions, `P.field op value` performs a graph lookup followed by a
comparison. If `P` is unbound, the graph is scanned for all subjects that have
the given predicate, and `P` is bound to each subject in turn.

---

## 7. Grammar Summary

```
program        → statement*
statement      → type_decl | binding | inference_rule | query | import | context_decl

type_decl      → TypeName [":" "(" parents ")"] NEWLINE INDENT field+ DEDENT
field          → identifier ":" type_expr NEWLINE

binding        → path ":=" value NEWLINE [annotations]
annotations    → INDENT annotation+ DEDENT
annotation     → "confidence" ":" conf_value
               | "provenance" ":" STRING
               | "fallback" ":" path
               | "context" ":" IDENTIFIER

inference_rule → rule_head "if" ":" NEWLINE INDENT condition+ DEDENT
rule_head      → IDENTIFIER "(" [arg ("," arg)*] ")"
condition      → predicate_call | comparison | "not" predicate_call

query          → "query" ":" predicate_call "?"
               | "find" VARIABLE+ "where" condition+

import         → "import" "*" "from" STRING

context_decl   → "context" IDENTIFIER ":" NEWLINE INDENT ctx_directive+ DEDENT
ctx_directive  → "confidence-threshold" ":" NUMBER
               | "error-tolerance" ":" ("zero"|"low"|"medium"|"high")
               | "extends" ":" IDENTIFIER

path           → IDENTIFIER ("." IDENTIFIER)*
               | IDENTIFIER "of" IDENTIFIER
value          → NUMBER | STRING | "true" | "false" | duration_lit
               | "[" value* "]" | "{" value* "}"
               | path | VARIABLE | arith_expr
duration_lit   → NUMBER DURATION_UNIT
arith_expr     → value ("+" | "-" | "*" | "/") value
conf_value     → "absolute" | NUMBER | "[" NUMBER "," NUMBER "]"

VARIABLE       → /[A-Z][A-Za-z0-9_-]*/
IDENTIFIER     → /[a-z][a-zA-Z0-9_-]*/
```
