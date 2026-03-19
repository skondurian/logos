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
pip install -e ".[dev]"
logos repl                          # interactive REPL
logos run examples/02_voting_rules.logos
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
make          # Python bootstrap → self-compile → build/logos_compile
make verify   # prove compile3 == compile4 (fixed point)
```

### Compile a program

```bash
# Using the shell driver (recommended):
bin/logoscc examples/02_voting_rules.logos -o /tmp/voting
/tmp/voting

# Or via the Python CLI:
logos compile examples/02_voting_rules.logos -o /tmp/voting --keep-c
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
| `Makefile` | Bootstrap + self-compile + install |
| `bin/logoscc` | End-to-end compilation driver script |

## Self-Hosting

The Logos compiler is self-hosted: `logos/compiler.logos` compiles Logos
source to C, and is itself compiled by the binary it produces. The build
process proves this fixed point:

```
Python codegen → logos_bootstrap (gen1)
logos_bootstrap → logos_compile.c (gen2, self-hosted C source)
cc logos_compile.c → logos_compile (gen3 binary)
logos_compile → logos_compile_check.c (gen4)
diff gen2 gen3 → identical  ✓
```

## Roadmap

- **Phases 0–10**: Python bootstrap interpreter ✅
- **Phase 11**: stdlib written in Logos ✅
- **Phase 12**: interpreter core written in Logos ✅
- **Phase 13 (v1.0)**: fully self-hosted — Logos interprets itself ✅
- **Binary compiler**: native compilation via self-hosted Logos→C transpiler ✅
