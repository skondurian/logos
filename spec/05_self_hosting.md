# Logos Self-Hosting

Logos v1.0 is fully self-hosted: the Logos compiler and interpreter are
written in Logos itself. This document describes the self-hosting architecture,
the bootstrap chain, and the proof of correctness.

---

## 1. What "Self-Hosted" Means

A self-hosted language is one where the compiler/interpreter is written in the
language itself. Logos achieves this in two directions:

1. **Interpreter:** `logos/interpreter.logos` reads, tokenizes, parses, and
   evaluates `.logos` files — without any Python.
2. **Compiler:** `logos/compiler.logos` translates `.logos` ASTs to C source
   code — producing the binary that compiles itself.

---

## 2. Self-Hosted Components

### `logos/lexer.logos` (364 lines)
Tokenizes Logos source strings into `[Type, Value]` token pairs.

- Entry: `lex-string(Source, Tokens)`
- Also: `lex-file(Path, Tokens)` via the `lex-file` primitive
- Handles: keywords (40+), identifiers, variables, strings, numbers,
  duration units, operators, indentation via `lex-file` primitive

### `logos/parser.logos` (443 lines)
Recursive descent parser producing tagged-list ASTs.

- Entry: `parse-tokens(Tokens, AST)`
- Produces `["program", Stmts]` with statement nodes
- Uses token consumption predicates: `tok-type`, `tok-kw`, `tok-ident`,
  `tok-var`, `tok-str`, `tok-num`, `skip-nl`, `tok-peek-type`
- Handles: bindings, rules, unit rules, queries, imports, type decls

### `logos/evaluator.logos` (94 lines)
Evaluates the AST produced by `parser.logos`.

- Entry: `eval-program(["program", Stmts])`
- Dispatches on AST tag:
  - `["bind", S, P, V]` → `assert-fact(S, P, V)`
  - `["unit", N, Args]` → `register-rule-ast(N, Args, [])`
  - `["rule", N, Args, Conds]` → `register-rule-ast(N, Args, Conds)`
  - `["query-bool", ...]` → `exec-bool-query-ast(...)`
  - `["query-find", ...]` → `exec-find-query-ast(...)`

### `logos/interpreter.logos` (32 lines)
Ties lexer + parser + evaluator together.

```logos
interpret(FilePath) if:
  lex-file(FilePath, Tokens)
  parse-tokens(Tokens, AST)
  eval-program(AST)
```

Run via: `logos interpret <file>`

### `logos/compiler.logos` (2112 lines)
Logos → C transpiler written in Logos. The largest and most complex
self-hosted module.

- Entry: `compile-file(InputPath)` — lex, parse, resolve imports, compile to C, write to stdout
- Entry: `compile-program(AST, CSource)` — compile AST to C string

Key subsystems:
- **`c-id`:** Convert Logos names to valid C identifiers (hyphen → underscore)
- **`dur-unit-secs`:** Compile-time duration unit table
- **`compile-binding`:** Generate `logos_graph_assert(...)` call for each fact
- **`compile-rule`:** Generate CPS rule functions + dispatcher
- **`head-unify-line`:** Generate `logos_unify(...)` for each head argument
- **`emit-condition`:** Generate CPS continuation chain for rule body conditions
- **`compile-bool-query`:** Generate `k_bool_capture` query in `main()`
- **`compile-find-query`:** Generate find-query scan in `main()`
- **`resolve-imports`:** Inline imports recursively (self-hosted)
- **`path-dirname`, `path-join`:** Path manipulation for import resolution

### `logos/compile-main.logos` (22 lines)
Binary entry point for the standalone compiler.

```logos
compile-main("done") if:
  argv(1, InputPath)
  compile-file(InputPath)
  write-stderr("done\n")

compile-main("done") if:
  write-stderr("error: compilation failed\n")

query: compile-main("done")?
```

Usage: `build/logos_compile input.logos > output.c`

---

## 3. The Bootstrap Chain

```
Generation 0 (Python codegen):
  python3 -m logos compile logos/compile-main.logos
      → build/logos_bootstrap.c   (Python-generated C, ~28k lines)
      → cc → build/logos_bootstrap

Generation 1 → 2 (first self-compile):
  build/logos_bootstrap logos/compile-main.logos
      → build/logos_compile.c     (Logos-generated C, ~28k lines)

Generation 2 (stable binary):
  cc build/logos_compile.c logos/runtime/*.c → build/logos_compile

Fixed-point proof (gen 2 → gen 3):
  build/logos_compile logos/compile-main.logos
      → build/logos_compile_check.c
  diff build/logos_compile.c build/logos_compile_check.c
      → 0 differences  ✓
```

The fixed point proves that the compiler output is **deterministic and
stable**: compiling the compiler source with itself produces identical output.

### Why the Fixed Point Matters

If gen2 ≠ gen3, it means the compiler is inconsistent — it generates different
code depending on whether it was compiled by Python or by itself. Equality
proves semantic consistency: both codegen strategies produce equivalent
programs.

---

## 4. Key Bug Fixed for Self-Hosting: Numeric Head Arguments

During self-hosting development, `build/logos_compile` (gen2 binary) failed
when compiling programs with duration facts (`age of alice := 30 years`).

**Root cause:** `compiler.logos` had:
```logos
head-unify-line(N, CName, KV, []) if: is-number(N)
```
This generated **no unification code** for numeric literals in rule head
positions. As a result, `dur-unit-secs("years", 31557600.0)` would match the
first argument but leave the second (the float value) unbound — so
`dur-to-secs` couldn't compute duration values, and compiling any program with
duration facts would fail.

**Fix:**
```logos
head-unify-line(N, CName, KV, [Line]) if:
  is-number(N)
  number-to-float-str(N, NS)
  str-concat3("    if (!logos_unify(env, var_", CName, ", logos_float(", LP)
  str-concat(LP, NS, LP2)
  str-concat(LP2, "))) return 0;", Line)
```

After this fix, gen2 correctly generates `logos_float(31557600.0)` unification
in `rule_dur_unit_secs_N`, and the fixed point holds.

---

## 5. Stack Depth Requirement

CPS recursion in the compiled compiler binary is deep. Compiling
`compile-main.logos` involves ~400+ statements across all imports, each adding
a CPS frame on the C stack.

On macOS, the default stack is 8 MB. This is exhausted during self-compilation,
causing a segfault. The fix: link with `-Wl,-stack_size,0x10000000` (256 MB).

This flag is applied:
- In `logos/compiler.py` (Python-generated binaries)
- In `Makefile` via `LDFLAGS` (the stable binary)
- In `bin/logoscc` (user programs compiled via the driver)

---

## 6. Import Resolution in the Self-Hosted Compiler

`compiler.logos` implements its own import resolver:

- `resolve-imports(InputPath, FlattenedStmts)` — reads, parses, and inlines
  all imports recursively
- `path-dirname(Path, Dir)` — extracts directory from a file path
- `path-join(Dir, File, Full)` — joins directory and filename
- `path-add-logos-ext(P, P2)` — adds `.logos` extension if absent
- `path-all-but-last(Path, Dir)` — drop last path component

This mirrors the Python `resolve_imports()` in `compiler.py`, implemented
purely in Logos.

---

## 7. Running the Self-Hosted Components

```bash
# Interpret a .logos file via Logos interpreter
logos interpret examples/02_voting_rules.logos

# Compile via native binary (uses logos_compile)
bin/logoscc examples/02_voting_rules.logos -o /tmp/voting
/tmp/voting

# Build everything from source
make clean && make

# Verify fixed point
make verify
```
