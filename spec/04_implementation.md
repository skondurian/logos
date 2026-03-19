# Logos Implementation Reference

---

## 1. Architecture Overview

Logos has two execution paths from the same source:

```
.logos source
    │
    ├─ [Python interpreter] ─────────────────────────────────────────────→ output
    │   lexer.py → parser.py → executor.py → inference.py
    │                                       → semantic_graph.py
    │
    └─ [Native compiler] ────────────────────────────────────────────────→ binary
        lexer.py → parser.py → codegen.py → cc → ELF/Mach-O
                    OR
        logos_compile (self-hosted) → C source → cc → ELF/Mach-O
```

---

## 2. Python Interpreter

### 2.1 Pipeline

| Stage | Module | Input → Output |
|---|---|---|
| Tokenization | `logos/lexer.py` | source string → token list |
| Parsing | `logos/parser.py` | token list → `Program` AST |
| Import resolution | `logos/compiler.py` | `Program` → flattened `Program` |
| Execution | `logos/executor.py` | `Program` → query outputs |

### 2.2 Modules

#### `logos/lexer.py`
Hand-written indentation-sensitive tokenizer. Produces synthetic `INDENT` /
`DEDENT` tokens based on a column stack (tabs = 4 spaces). Token types:
`KEYWORD`, `IDENTIFIER`, `VARIABLE`, `NUMBER`, `STRING`, `DURATION_UNIT`,
`INDENT`, `DEDENT`, `NEWLINE`, operators, punctuation.

Key functions:
- `tokenize(source) → list[Token]`
- `tokenize_raw(source) → list[Token]` (includes COMMENT/WHITESPACE)

#### `logos/parser.py`
Hand-written recursive descent parser. Produces `ast_nodes.py` dataclasses.
No backtracking — each `parse_*` method consumes exactly what it expects or
raises `ParseError`.

Key entry points:
- `parse_file(path) → Program`
- `parse_source(source) → Program`

#### `logos/ast_nodes.py`
Pure dataclasses, no logic. All AST node types:

```
DurationLit, SetLit, ListLit, Path, Variable, ArithExpr
ConfidenceAnnotation, Annotations, FallbackEntry
TypeExpr, FieldDecl, TypeDecl
SemanticBinding, Retraction
PredicateCall, Comparison, NegatedPredicate, InferenceRule
TransformDecl, ContextDecl
BoolQuery, FindQuery, ImportStmt
Program
```

#### `logos/executor.py`
Orchestrates program execution. Manages:
- `TypeLattice` — type declarations
- `SemanticGraph` — fact storage
- `ContextRegistry` — active contexts
- `list[InferenceRule]` — registered rules
- `InferenceEngine` — proof search

Statement dispatch:
- `TypeDecl` → register in lattice
- `SemanticBinding` → evaluate value, assert `FactNode`
- `InferenceRule` → append to rules list
- `ContextDecl` → register context
- `BoolQuery` → prove, OR-combine all proof confidences
- `FindQuery` → prove_all, group by bindings, OR-combine per group
- `ImportStmt` → recursively load file

#### `logos/inference.py`
SLD resolution engine (backward chaining).

```python
def prove(goal, depth=0, bindings={}) → Iterator[Proof]:
    # 1. Check primitive predicates
    # 2. Lookup matching facts in SemanticGraph
    # 3. For each matching rule:
    #    a. Unify goal with rule head (with fresh variable renaming)
    #    b. prove_all(conditions) with updated bindings
    #    c. Yield each successful sub-proof
```

- Variables are renamed per rule invocation (`X` → `X__0`, `X__1`, ...) to
  prevent scope collisions.
- Confidence accumulates via conjunction across conditions; multiple paths via
  disjunction.
- `MAX_DEPTH = 256` prevents infinite recursion.
- Negation as failure: `not P` succeeds iff `prove(P)` yields nothing.

Unification (`unify_term`):
- Uppercase single-part paths treated as variables.
- `walk(term, bindings)` chases variable chains.
- No occurs check (infinite terms possible but not used in practice).

#### `logos/confidence.py`
Beta distribution model for confidence values.

```python
ConfidenceValue:
  .point: float          # modal value [0,1]
  .lower: float          # 95% CI lower bound
  .upper: float          # 95% CI upper bound
  .alpha: float          # Beta α parameter
  .beta_param: float     # Beta β parameter
```

Operations:
- `.conjoin(other)` — `P(A∧B) = P(A) × P(B)`
- `.disjoin(other)` — `P(A∨B) = 1 − (1−P(A))(1−P(B))`
- `.degrade(factor=0.95)` — per-inference-step decay

Construction:
- `ConfidenceValue.absolute()` — Dirac at 1.0
- `ConfidenceValue.from_point(p)` — Beta mode at p, concentration 20
- `ConfidenceValue.from_interval(lo, hi)` — Beta fitted to 95% CI

#### `logos/semantic_graph.py`
Directed multigraph of `FactNode`s. Each node carries:
- `subject`, `predicate`, `value`, `value_type` — the fact content
- `confidence: ConfidenceValue` — certainty
- `provenance: list[ProvenanceRecord]` — derivation history
- `derived_from: list[UUID]` — dependency edges
- `context_name: str | None` — context scope
- `retracted: bool` — logical deletion flag

Operations:
- `assert_fact(fact)` — adds fact; warns (`ContradictionWarning`) on conflict
- `query(subject, predicate) → QueryResult` — returns active (non-retracted) facts
- `retract(subject, predicate)` — marks as retracted, preserves history
- `merge(other)` — union two graphs

#### `logos/type_system.py`
`TypeLattice` — networkx `DiGraph` where edges represent IS-A relationships.

Built-in hierarchy:
```
Entity
├── Number
│   ├── Integer
│   └── Float
├── Text
│   └── HumanName
├── Boolean
├── Duration
├── Timestamp
├── GeoLocation
├── URL
├── Set
├── List
└── Optional
```

Operations:
- `is_subtype_of(child, parent) → bool` — transitive via `nx.has_path`
- `ancestors(name) → set[str]` — all supertypes
- `all_fields(name) → dict[str, FieldInfo]` — inherited fields, own fields take priority
- `lca(a, b) → str` — least common ancestor

#### `logos/context.py`
`ContextRegistry` — named partitions with confidence thresholds.

- `register(ctx)` — add context, validate parent references
- `activate(name)` / `deactivate(name)` — control active contexts
- `effective_threshold(name) → float` — resolve inheritance chain (max threshold)
- `effective_tolerance(name) → float` — resolve error tolerance

Error tolerance levels: `zero=0.0`, `low=0.1`, `medium=0.3`, `high=0.7`.

#### `logos/primitives.py`
Python-side primitive predicates. Registered via `@primitive("name")` decorator.
Signature: `fn(args, bindings, engine) → Iterator[Proof]`.

Covers: string ops, numeric ops, list ops, I/O, assert-fact.

#### `logos/errors.py`

```
LogosError
├── ParseError
├── TypeError
├── ConfidenceError
├── InferenceError
│   ├── CycleDetectedError
│   ├── DepthLimitError
│   └── UnificationError
├── ContextError
├── ExecutionError
└── LogosImportError

ContradictionWarning (UserWarning)
```

#### `logos/compiler.py`
Import resolution and C compilation driver.

- `resolve_imports(program, base_dir) → Program` — inline all imports
  recursively; detects and rejects circular imports
- `compile_file(logos_path, output_path, cc, keep_c) → None` — parse, generate
  C via `codegen.py`, invoke `cc`; adds `-Wl,-stack_size,0x10000000` on macOS
  for the 256 MB stack needed by deep CPS recursion

#### `logos/codegen.py`
Python → C transpiler. `Compiler(program).generate() → str` produces a complete
C translation unit.

Generated C structure:
1. `#include` and preamble
2. Forward declarations for all rule dispatchers
3. Rule functions: `rule_NAME_N(env, args..., k)` — one per clause
4. Dispatcher: `pred_NAME(env, args..., k)` — tries all clauses in order
5. `logos_setup(graph)` — asserts all facts from semantic bindings
6. `main()` — initializes env/graph, calls setup, executes queries

CPS (continuation-passing style) backtracking:
```c
// Dispatcher tries each clause with mark/undo:
int pred_can_vote(logos_env *env, logos_term var_P, logos_cont k) {
    logos_mark_t m = logos_mark(env);
    if (rule_can_vote_0(env, var_P, k)) return 1;
    logos_undo(env, m);
    // ... try next clause ...
    return 0;
}
```

#### `logos/repl.py`
Interactive REPL and CLI entry point (`python3 -m logos`).

Subcommands:
- `logos repl` — interactive session with prompt_toolkit
- `logos run <file>` — run and print output
- `logos interpret <file>` — run via self-hosted interpreter
- `logos compile <file> [-o output] [--keep-c] [--cc=cc]` — compile to binary

---

## 3. Self-Hosted Compiler

The Logos compiler is written in Logos itself. This enables the self-hosting
chain described below.

### 3.1 Self-Hosted Modules

| File | Role | Entry Point |
|---|---|---|
| `logos/lexer.logos` | Tokenizer | `lex-string(Source, Tokens)` |
| `logos/parser.logos` | Parser | `parse-tokens(Tokens, AST)` |
| `logos/evaluator.logos` | Evaluator | `eval-program(AST)` |
| `logos/interpreter.logos` | Full interpreter pipeline | `interpret(FilePath)` |
| `logos/compiler.logos` | Logos → C transpiler | `compile-file(Path)`, `compile-program(AST, C)` |
| `logos/compile-main.logos` | Binary entry point | reads argv[1], writes C to stdout |

### 3.2 AST Format (parser.logos output)

Tagged lists compatible with evaluator.logos and compiler.logos:

| Tag | Fields | Meaning |
|---|---|---|
| `["program", Stmts]` | statement list | Root node |
| `["bind", Subj, Pred, Val]` | — | Semantic binding |
| `["rule", Name, Args, Conds]` | — | Inference rule |
| `["unit", Name, Args]` | — | Unit rule (no conditions) |
| `["query-bool", Name, Args]` | — | Boolean query |
| `["query-find", Vars, Conds]` | — | Find query |
| `["import", ...]` | — | Import (skipped by compiler) |
| `["skip-type-decl", ...]` | — | Type decl (skipped) |
| `["call", Name, Args]` | — | Predicate call condition |
| `["not-call", Name, Args]` | — | Negated predicate condition |
| `["cmp", Left, Op, Right]` | — | Comparison condition |

### 3.3 CPS Generation in compiler.logos

`compiler.logos` (2112 lines) generates CPS-style C for each rule:

1. **Head unification:** Each head argument position generates a `logos_unify`
   call to bind/check the argument against the passed `logos_term`.
2. **Condition chain:** Conditions are chained as nested CPS continuations.
   Each condition calls the next via a heap-allocated context struct.
3. **Dispatchers:** One dispatcher per predicate name tries each clause in
   order, bracketing with `logos_mark` / `logos_undo`.
4. **Queries:** Boolean queries use `k_bool_capture`; find queries scan and
   print matched bindings.

### 3.4 Self-Hosting Bootstrap Chain

```
[Python codegen]
    logos/compile-main.logos → build/logos_bootstrap.c → cc → logos_bootstrap

[Self-compile gen2]
    logos_bootstrap  logos/compile-main.logos → build/logos_compile.c

[Stable binary]
    cc build/logos_compile.c → build/logos_compile

[Fixed-point proof]
    build/logos_compile logos/compile-main.logos → logos_compile_check.c
    diff logos_compile.c logos_compile_check.c → identical ✓
```

`make verify` runs the fixed-point check and reports `PASS` or `FAIL`.

---

## 4. C Runtime Library

Lives in `logos/runtime/`. Linked into every compiled Logos binary.

### 4.1 Term Representation (`logos_runtime.h`)

```c
typedef struct {
    int tag;              // LOGOS_INT, LOGOS_FLOAT, LOGOS_STRING,
                          // LOGOS_BOOL, LOGOS_DURATION, LOGOS_VAR,
                          // LOGOS_LIST, LOGOS_NIL
    union {
        long        i;    // LOGOS_INT, LOGOS_BOOL
        double      f;    // LOGOS_FLOAT, LOGOS_DURATION
        const char *s;    // LOGOS_STRING (interned)
        int         var_id; // LOGOS_VAR
        logos_cons *cons; // LOGOS_LIST
    };
} logos_term;
```

All strings are **interned**: `logos_intern(s)` returns a canonical pointer.
String equality is pointer equality.

### 4.2 Execution Environment

```c
typedef struct logos_env {
    logos_bindings bindings;  // variable binding array (32768 slots)
    logos_trail    trail;     // undo log (262144 entries)
    logos_graph   *graph;     // fact store
    double         confidence; // accumulated confidence
    void          *capture_found; // output slot for bool queries
    void          *capture_conf;  // output slot for confidence
} logos_env;
```

### 4.3 Backtracking

```c
logos_mark_t logos_mark(logos_env *env);        // save trail top
void         logos_undo(logos_env *env, logos_mark_t mark); // restore bindings
```

The trail records which variable IDs were bound since the last mark. `undo`
clears those bindings, restoring the state for the next choice point.

### 4.4 Unification

```c
int logos_unify(logos_env *env, logos_term a, logos_term b);
```

- Walks variable chains in both arguments.
- Binds `LOGOS_VAR` to the other term; records on trail.
- STRING: interned pointer equality.
- DURATION: float equality.
- LIST: recursive element-by-element.
- Type mismatch: returns 0 (failure).

### 4.5 Fact Store

```c
void logos_graph_assert(logos_graph *g, const char *subj, const char *pred,
                         logos_term val, double conf);
int  logos_graph_lookup(logos_graph *g, const char *subj, const char *pred,
                         logos_term *out, double *conf_out);
int  logos_graph_scan(logos_graph *g, const char *pred, logos_env *env,
                       logos_scan_cb cb, logos_cont k);
```

`logos_graph_scan` iterates all facts with the given predicate. For each
matching fact it attempts to bind the subject variable (if unbound) and invokes
the callback continuation. This is used by the CPS code for path lookups
where the subject may be unbound (find queries).

### 4.6 Confidence

```c
double logos_conjoin(double a, double b);   // a * b
double logos_disjoin(double a, double b);   // 1 - (1-a)*(1-b)
double logos_degrade(double c);             // c * 0.95
```

### 4.7 Runtime Files

| File | Size | Content |
|---|---|---|
| `logos_runtime.h` | 147 lines | Type definitions, all function declarations |
| `logos_runtime.c` | 476 lines | Core: interning, unification, backtracking, graph, confidence |
| `logos_primitives.h` | 120 lines | Primitive predicate declarations (40+ predicates) |
| `logos_primitives.c` | 651 lines | Primitive implementations: strings, numerics, lists, I/O |
| `logos_meta.h` | 44 lines | Meta-interpreter declarations |
| `logos_meta.c` | 577 lines | Meta-interpreter: dynamic rule registration, AST execution |
| `logos_lexer.h` | 26 lines | Lexer runtime declarations |
| `logos_lexer.c` | 299 lines | File/string tokenizer (used by self-hosted compiler) |

**Total runtime:** ~2,340 lines of C.

---

## 5. Build System

### 5.1 Makefile Targets

| Target | Action |
|---|---|
| `make` | Full build: Python bootstrap → self-compile → `build/logos_compile` |
| `make bootstrap` | Python bootstrap only → `build/logos_bootstrap` |
| `make verify` | Prove fixed point: compile3 == compile4 |
| `make install` | Install to `PREFIX` (default `/usr/local`) |
| `make test` | Run test suite (`python3 -m pytest tests/ -q`) |
| `make clean` | Remove `build/` |

### 5.2 Build Steps

```makefile
# Step 1: Python → bootstrap binary
python3 -m logos compile logos/compile-main.logos --keep-c -o build/logos_bootstrap

# Step 2: bootstrap → stable self-hosted C source
build/logos_bootstrap logos/compile-main.logos > build/logos_compile.c

# Step 3: C → native binary
cc build/logos_compile.c logos/runtime/*.c -Ilogos/runtime \
   -o build/logos_compile -O2 -lm -Wl,-stack_size,0x10000000   # macOS
```

The 256 MB stack flag (`-Wl,-stack_size,0x10000000`) is required on macOS
because the CPS-style rule functions recurse deeply: compiling
`compile-main.logos` (which imports `compiler.logos` → `parser.logos` →
`stdlib/lists` → `stdlib/strings`) generates ~400+ statements that each add a
CPS frame, exhausting the default 8 MB stack.

### 5.3 Install Layout

```
PREFIX/
  bin/
    logoscc                    # shell driver script
  lib/logos/
    logos_compile              # native compiler binary
    runtime/
      logos_runtime.c/.h
      logos_primitives.c/.h
      logos_meta.c/.h
      logos_lexer.c/.h
```

### 5.4 `bin/logoscc` Driver

```
Usage: logoscc <input.logos> [-o output] [--keep-c] [--cc=<compiler>]
```

Resolves `logos_compile` binary in priority order:
1. `$LOGOS_COMPILE` environment variable
2. `build/logos_compile` (relative to repo root)
3. `__LOGOS_LIB__/logos_compile` (substituted at install time)

Pipeline:
```bash
logos_compile input.logos > /tmp/logos_XXXXXX.c   # Logos → C
cc /tmp/logos_XXXXXX.c runtime/*.c -o output -O2 -lm [-Wl,-stack_size,...]
```

---

## 6. Test Suite

311 tests across 22 files (`python3 -m pytest tests/ -q`).

| File | Tests | Coverage |
|---|---|---|
| `test_lexer.py` | lexer | Tokenization, indentation, INDENT/DEDENT |
| `test_parser.py` | parser | AST construction, all node types |
| `test_type_system.py` | type_system | Subtype checking, field inheritance, LCA |
| `test_confidence.py` | confidence | Arithmetic, Beta distribution, fallback chains |
| `test_contexts.py` | context | Registration, activation, threshold inheritance |
| `test_inference.py` | inference | SLD resolution, unification, NAF, depth limit |
| `test_executor.py` | executor | Statement dispatch, program loading |
| `test_primitives.py` | primitives | All 40+ native predicates |
| `test_or_aggregation.py` | inference | Multiple proof paths, OR-combination |
| `test_imports.py` | compiler | Import flattening, circular import detection |
| `test_compiler.py` | codegen + compiler | C generation, binary compilation |
| `test_var_compare.py` | inference/codegen | Variable comparisons in rule bodies |
| `test_phase1.py` | end-to-end | Import flattening |
| `test_phase2.py` | end-to-end | Core primitives (list, equal, num-add) |
| `test_phase3.py` | end-to-end | String primitives |
| `test_phase5.py` | end-to-end | List head pattern matching |
| `test_phase6.py` | end-to-end | assert-fact, zero-arity predicates |
| `test_phase7.py` | end-to-end | Variable comparisons in compiled code |
| `test_phase8.py` | end-to-end | Full pipeline integration |
| `test_lexer_logos.py` | lexer.logos | Self-hosted tokenizer |
| `test_parser_logos.py` | parser.logos | Self-hosted parser |
| `test_evaluator_logos.py` | evaluator.logos | Self-hosted evaluator |
