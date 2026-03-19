# Logos

**Logos** is an AI-native programming language designed from first principles for reasoning under uncertainty. It treats execution as inference, values as probabilistic facts, and programs as semantic knowledge graphs.

## Core Ideas

- **Ontological types** — types describe *what things are*, not just their shape
- **Semantic bindings** — you assert facts, not assign variables
- **Confidence propagation** — every value carries a probability distribution
- **Dependency-graph execution** — the runtime is a directed semantic graph, not a call stack
- **Inference rules** — computation is backward-chaining SLD resolution

## Quick Start

```bash
# Build the native compiler (no Python required)
make

# Compile and run a Logos program
bin/logoscc examples/02_voting_rules.logos -o /tmp/voting
/tmp/voting
```

## Example

```logos
Person:
  name: HumanName
  age: Duration

age of alice := 30 years
  confidence: absolute
  provenance: "birth-record"

citizenship of alice := "US"
  confidence: absolute

can-vote(P) if:
  P.age >= 18 years
  P.citizenship = "US"

query: can-vote(alice)?
```

Output:
```
can-vote(alice): true  [confidence: 0.950]
```

## Native Binary Compilation

Logos programs can be compiled to native binaries via a self-hosted compiler
(the Logos compiler is written in Logos and compiles itself).

### Build the compiler

```bash
make          # bootstrap seed → build/logos_compile (no Python needed)
make verify   # prove compile3 == compile4 (fixed point)
```

The build is Python-free on a fresh checkout: `bootstrap/logos_compile.c` is
a committed seed that lets the compiler bootstrap without any Python tooling.
If a binary already exists it self-compiles instead, keeping the build
reproducible and fast.

### Compile a program

```bash
# Using the shell driver (recommended):
bin/logoscc examples/02_voting_rules.logos -o /tmp/voting
/tmp/voting
```

### Install system-wide

```bash
make install          # installs to /usr/local/bin/logoscc
make install PREFIX=~/.local
logoscc myprogram.logos -o myprogram
```

The generated binary links against a small C runtime (`logos/runtime/`) that
handles unification, backtracking via trail marks, the semantic graph, and
confidence arithmetic. No WAM or LLVM required.

### Interpreter

```bash
build/logos_interpret examples/02_voting_rules.logos
```

`build/logos_interpret` is a self-hosted interpreter built alongside the
compiler. It evaluates Logos programs without generating a binary.

## Running Tests

```bash
make test        # shell-based integration tests (no Python needed)
```

The test suite in `tests/logos/` compiles each `.logos` file with
`bin/logoscc` and compares stdout to a `.expected` file.

## Architecture

| Module | Role |
|---|---|
| `grammar.lark` | Lark EBNF grammar (Earley parser) |
| `ast_nodes.py` | Pure dataclasses for all AST nodes |
| `semantic_graph.py` | NetworkX DiGraph of FactNodes |
| `type_system.py` | Type lattice with subtype checking |
| `confidence.py` | ConfidenceValue with Beta distribution arithmetic |
| `inference.py` | SLD-resolution backchaining engine |
| `executor.py` | Orchestration pipeline |
| `repl.py` | Interactive REPL and CLI entry point |
| `codegen.py` | Python → C transpiler (CPS-based) |
| `compiler.py` | Python compiler driver (`logos compile`) |
| `logos/compiler.logos` | Self-hosted Logos → C compiler |
| `logos/parser.logos` | Self-hosted Logos parser |
| `logos/runtime/` | C runtime library (unification, graph, backtracking) |
| `bootstrap/logos_compile.c` | Committed seed C source (enables Python-free builds) |
| `Makefile` | Bootstrap + self-compile + install |
| `bin/logoscc` | End-to-end compilation driver script |

## Self-Hosting

The Logos compiler is self-hosted: `logos/compiler.logos` compiles Logos
source to C, and is itself compiled by the binary it produces. The build
process proves this fixed point:

```
bootstrap/logos_compile.c (seed)  — committed, no Python needed
cc logos_compile.c → logos_compile (binary)
logos_compile → logos_compile_check.c (self-compiled C)
diff seed check → identical  ✓
```

To regenerate the bootstrap seed from the current binary:
```bash
make update-bootstrap
```

## Development

The Python interpreter and pytest suite are retained for development use:

```bash
pip install -e ".[dev]"
logos repl                          # interactive REPL
logos run examples/02_voting_rules.logos
make test-python                    # run Python pytest suite
```

Python is only required for `make test-python` (development) or if
bootstrapping from scratch without the committed seed.

## Specification

Full documentation lives in [`spec/`](spec/):

| Document | Contents |
|---|---|
| [Language Reference](spec/01_language.md) | Syntax, types, confidence, queries, grammar |
| [Primitives](spec/02_primitives.md) | All 40+ built-in predicates |
| [Standard Library](spec/03_stdlib.md) | lists, strings, math, io |
| [Implementation](spec/04_implementation.md) | Interpreter, C runtime, build system, tests |
| [Self-Hosting](spec/05_self_hosting.md) | Bootstrap chain and fixed-point proof |

## Roadmap

- **Phases 0–10**: Python bootstrap interpreter ✅
- **Phase 11**: stdlib written in Logos ✅
- **Phase 12**: interpreter core written in Logos ✅
- **Phase 13 (v1.0)**: fully self-hosted — Logos interprets itself ✅
- **Binary compiler**: native compilation via self-hosted Logos→C transpiler ✅
- **Python-free build**: bootstrap seed committed, no Python required for `make` ✅
