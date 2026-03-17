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
can-vote(alice) → TRUE  [confidence: 1.000]
```

## Architecture

| Module | Role |
|---|---|
| `grammar.lark` | Lark EBNF grammar (Earley parser) |
| `ast_nodes.py` | Pure dataclasses for all AST nodes |
| `semantic_graph.py` | NetworkX DiGraph of FactNodes |
| `type_system.py` | Type lattice with subtype checking |
| `confidence.py` | ConfidenceValue with Beta distribution arithmetic |
| `inference.py` | SLD-resolution backchaining engine |
| `context.py` | Context hierarchy and threshold filtering |
| `executor.py` | Orchestration pipeline |
| `repl.py` | Interactive REPL with syntax highlighting |

## Specification

See `spec/` for the full language specification.

## Roadmap

- **Phases 0–10**: Python bootstrap interpreter
- **Phase 11**: stdlib written in Logos
- **Phase 12**: interpreter core written in Logos
- **Phase 13 (v1.0)**: fully self-hosted — Logos interprets itself
