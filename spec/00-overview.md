# Logos Language Specification — Chapter 0: Overview

## 1. Introduction

Logos is a declarative programming language designed for reasoning under uncertainty. It is intended as a substrate for AI systems and human analysts who must draw conclusions from incomplete, conflicting, or probabilistic information. Unlike conventional programming languages where every value is either known or unknown, every fact in Logos carries an associated **confidence value** that propagates automatically through all inference chains.

Logos occupies a position between traditional logic programming (Prolog), probabilistic graphical models, and semantic-web knowledge representation (RDF/OWL). It borrows the rule-and-query model from Prolog, the typed entity-relationship model from OWL, and the probabilistic semantics from Bayesian inference — but unifies them into a single coherent language with clean syntax and a well-defined execution model.

## 2. Design Goals

| Goal | Description |
|------|-------------|
| **Confidence-first** | Every fact and derived conclusion carries a confidence value. Certainty is a special case, not the default. |
| **Semantic clarity** | Bindings read like English prose (`age of alice := 30 years`). The code is its own documentation. |
| **Ontological precision** | Types form an IS-A lattice. Domain modeling is a first-class activity, not an afterthought. |
| **Execution as inference** | Running a Logos program is indistinguishable from performing logical inference over a knowledge graph. |
| **Provenance tracking** | Every fact knows where it came from, when it was asserted, and who asserted it. |
| **Contradiction tolerance** | Conflicting facts coexist with their respective provenances; the runtime does not crash or overwrite. |
| **Human and AI legible** | Logos files are valid, readable documents — not just source code. An LLM can reason about a Logos knowledge base by reading it directly. |

## 3. Target Audience

Logos is designed for two primary audiences:

**AI systems** — Language models, reasoning agents, and automated pipelines that must maintain structured beliefs about the world, update those beliefs as evidence arrives, and answer queries with calibrated confidence.

**Human analysts** — Domain experts in law, medicine, finance, intelligence analysis, and policy who need to formalize their reasoning, share it with colleagues, and have it checked for consistency.

Both audiences benefit from the same core property: Logos makes the structure of reasoning explicit and inspectable at every level.

## 4. Key Innovations

### 4.1 Execution-as-Inference

In Logos there is no distinction between "running the program" and "querying the knowledge base." Evaluation proceeds by backchaining inference (SLD-resolution) over the semantic graph. A `find` expression is a query; evaluating a module is populating and querying the same graph.

### 4.2 Semantic Bindings

Facts are stated in subject-predicate-object form that reads naturally:

```logos
age of alice := 30 years
nationality of alice := "American"
employer of alice := acme-corp
```

These are not variable assignments. They are immutable assertions into the knowledge graph. Multiple assertions about the same subject-predicate pair coexist with distinct provenances rather than overwriting each other.

### 4.3 Ontological Types

Every entity belongs to one or more types arranged in an IS-A lattice. Types declare fields, and field values are inherited through the lattice. This allows precise domain modeling without sacrificing flexibility.

```logos
type Person IS-A Entity
  fields:
    name: HumanName
    age: Duration
    nationality: Text

type Employee IS-A Person
  fields:
    employer: Organization
    salary: Money
```

### 4.4 Confidence Propagation

Every fact may carry a confidence annotation. If omitted, confidence defaults to the "absolute" value (Dirac delta at 1.0). Inference rules combine confidences using product semantics for conjunction and probabilistic-or semantics for disjunction.

```logos
age of alice := 30 years [confidence: 0.95]
age of bob   := 25 years [confidence: 0.80]
```

When an inference rule fires using both facts, the derived conclusion's confidence is at most `0.95 × 0.80 = 0.76`, further reduced by a per-rule degradation factor.

### 4.5 Dependency-Graph Execution

The runtime maintains an explicit directed acyclic graph (DAG) of dependencies between facts and derived conclusions. When a base fact is retracted or updated, all downstream conclusions are automatically invalidated and re-evaluated. This enables incremental, reactive reasoning.

### 4.6 Provenance Records

Every binding carries a provenance record:

```logos
age of alice := 30 years [
  confidence: 0.95
  source: "DMV database"
  asserted-at: 2026-01-15
  asserted-by: data-import-agent
]
```

Provenance is queryable: `find source of (age of alice)`.

## 5. Feature Summary

| Feature | Status | Notes |
|---------|--------|-------|
| Ontological types (IS-A lattice) | Core | Multiple inheritance |
| Semantic bindings | Core | Immutable fact assertions |
| Confidence values | Core | Point + 95% CI + distribution |
| Inference rules | Core | SLD backchaining |
| Provenance tracking | Core | Per-binding metadata |
| Contradiction handling | Core | Both facts retained |
| Duration arithmetic | Core | `30 years + 6 months` |
| HumanName type | Core | Structured name handling |
| Fallback chain operator `\|` | Core | `X \| Y \| default` |
| `find` query form | Core | Returns bindings with confidence |
| Negation-as-failure | Core | `not: condition` |
| Module system | Planned | Namespace isolation |
| Temporal reasoning | Planned | Valid-time intervals |
| Probabilistic programs | Planned | Sampling-based inference |

## 6. Hello World Example

The following complete Logos program demonstrates the core language features. It models a small knowledge base about people, asks whether they are eligible to vote, and queries the result.

```logos
// hello-world.logos
// A minimal Logos program demonstrating core features.

// --- Type declarations ---

type Person IS-A Entity
  fields:
    name: HumanName
    age: Duration
    nationality: Text

type Citizen IS-A Person
  fields:
    country: Text

// --- Facts ---

name of alice := { first: "Alice", last: "Smith" }
age of alice  := 30 years
nationality of alice := "American"

name of bob := { first: "Bob", last: "Jones" }
age of bob  := 16 years [confidence: 0.85]
nationality of bob := "American"

name of carlos := { first: "Carlos", last: "Reyes" }
age of carlos := 45 years
nationality of carlos := "Mexican"

// --- Inference rules ---

can-vote(P) if:
  age of P >= 18 years
  nationality of P == "American"

// --- Query ---

find P where can-vote(P)
```

**Expected output:**

```
Results for: find P where can-vote(P)

  alice  [confidence: absolute]
  bob    [confidence: 0.85]  // age assertion was uncertain

2 result(s). bob included because age confidence > threshold (default: 0.5).
```

Notice that `bob` appears in results but with the confidence inherited from his age assertion. `carlos` does not appear because his nationality does not match, regardless of confidence.

## 7. File Format

Logos source files use the `.logos` extension. Files are UTF-8 encoded. The language is whitespace-significant: indentation (2 or 4 spaces, consistent within a file) delimits blocks.

## 8. Relationship to Other Systems

| System | Relationship |
|--------|-------------|
| Prolog | Logos uses SLD-resolution backchaining; syntax is more readable |
| RDF/OWL | Logos uses a semantic graph runtime; types correspond to OWL classes |
| Datomic | Logos facts are immutable datoms with provenance; similar append-only model |
| ProbLog | Logos confidence model is similar but uses continuous distributions |
| Datalog | Logos rules are Datalog-like but support function terms and duration arithmetic |
| YAML/JSON | Logos knowledge bases can be serialized to/from JSON-LD |

## 9. Specification Structure

This specification is organized into the following chapters:

| Chapter | Topic |
|---------|-------|
| 00 | Overview (this document) |
| 01 | Philosophy and epistemological foundations |
| 02 | Lexical structure |
| 03 | Ontological type system |
| 04 | Semantic bindings |
| 05 | Confidence model |
| 06 | Inference rules |
| 07 | Query language *(planned)* |
| 08 | Module system *(planned)* |
| 09 | Standard library *(planned)* |
| 10 | Runtime and execution model *(planned)* |
