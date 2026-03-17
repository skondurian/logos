# Logos Language Specification — Chapter 1: Philosophy

## 1. Why Traditional Programming Languages Fail for AI Reasoning

General-purpose programming languages — Python, Java, Haskell, even Prolog in its conventional use — make a foundational assumption that does not hold in AI reasoning contexts: **facts are either known or unknown**. A variable either has a value or it does not. A function either returns a result or raises an exception. The world is closed: what is not asserted is false.

This closed-world assumption (CWA) is catastrophically wrong for the domains where AI systems operate. Consider:

- A medical diagnosis system that must reason about a patient's history when only partial records are available.
- An intelligence analysis platform that must weigh conflicting reports from sources of varying reliability.
- A legal reasoning system that must evaluate arguments under conditions of genuine normative uncertainty.
- A financial risk model that must combine quantitative data with qualitative expert judgment.

In all these cases, the appropriate response to missing or conflicting information is not to crash, return null, or raise an exception — it is to **reason with calibrated uncertainty and make the uncertainty explicit**.

### 1.1 The Null Problem

In languages with nullable types or None/null values, missing information is represented by the absence of a value. This forces every consumer of information to perform null checks, and it collapses the distinction between "we checked and found nothing" and "we never checked." A null age is not the same as an age of zero, nor is it the same as an unknown age. But null cannot distinguish these cases.

Logos replaces null with the open-world assumption (OWA): the absence of a binding for `age of alice` means the age is unknown, not that Alice has no age. A query for `age of alice` returns either a binding with confidence, or the explicit result "no binding found" — which is itself information.

### 1.2 The Overwrite Problem

In mutable-variable languages, updating a fact destroys the previous value. When we learn that Alice's age was previously estimated at 28 and is now confirmed at 30, the conventional approach is to overwrite 28 with 30. But this destroys information:

- The 28 came from a particular source.
- The 30 came from a different, more reliable source.
- The discrepancy between 28 and 30 is itself evidence about the quality of the original source.
- A downstream system that cached the age-28 conclusion should be invalidated.

Logos solves this by making facts **immutable assertions with provenance**. The knowledge graph retains both the 28 and the 30, each with its source. Inference rules may combine them, prioritize by confidence, or flag the contradiction. Nothing is silently lost.

### 1.3 The Confidence Blindness Problem

Even probabilistic programming languages (Stan, PyMC, Edward) typically compute over probabilities as ordinary floating-point numbers without attaching confidence information to the probabilities themselves. A probability of 0.7 computed from 1000 data points is very different from a probability of 0.7 derived from 3 data points — but conventional probabilistic programs cannot represent this distinction without ad hoc metadata.

Logos builds **second-order uncertainty** into the confidence model: every confidence value is a distribution over [0,1], not a point estimate. The width of that distribution represents our uncertainty about the confidence itself.

## 2. Epistemological Foundations

### 2.1 Bayesian Inference

The confidence model in Logos is grounded in Bayesian probability theory. A confidence value represents a **degree of belief** in a proposition, not a frequency in a reference class (frequentist interpretation) or a propensity of an event to occur (propensity interpretation).

The Bayesian interpretation supports several key language features:

- **Prior beliefs** can be stated as initial confidence annotations.
- **Evidence updates** narrow the confidence interval without replacing the prior.
- **Conjunction** of independent evidence combines multiplicatively (`P(A ∧ B) = P(A) × P(B)` under independence).
- **Disjunction** combines using the inclusion-exclusion principle (`P(A ∨ B) = P(A) + P(B) − P(A)P(B)`).

Logos does not implement full Bayesian updating (that would require a generative model), but its confidence arithmetic is consistent with Bayesian principles and produces reasonable results for the common case of independent evidence sources.

### 2.2 Semantic Web Inspiration

Logos inherits the **subject-predicate-object triple** as its fundamental data model from RDF (Resource Description Framework). Every binding in Logos is a triple:

```
(subject, predicate, object)
```

Where:
- **subject** is an entity identifier
- **predicate** is a field or relation name
- **object** is a value or another entity identifier

This triple model has a profound consequence: the knowledge base is a **labeled directed graph**, not a collection of records. Queries navigate this graph by following edges, not by joining tables. The expressive power of graph navigation is far higher than relational joins for domains with complex, irregular structure.

Logos diverges from RDF in two important ways: it adds a typed IS-A lattice (inspired by OWL), and it extends triples to quads by adding provenance metadata as a first-class fourth component.

### 2.3 Logic Programming Heritage

Logos's inference engine descends from Prolog's SLD-resolution. The core idea — that a program is a set of Horn clauses and evaluation is theorem proving — provides a clean, compositional semantics for inference rules.

However, Logos departs from Prolog in several ways:

| Prolog | Logos |
|--------|-------|
| Closed-world assumption | Open-world assumption |
| No confidence model | First-class confidence propagation |
| Untyped terms | Ontological IS-A type lattice |
| No provenance | Per-fact provenance records |
| Mutation via `assert`/`retract` is uncontrolled | Retraction is logged and downstream conclusions invalidated |
| Backtracking is implicit | Inference graph is explicit and inspectable |

The key insight from logic programming that Logos preserves is: **a query is a theorem to be proved, and proving it means finding a binding for its free variables that satisfies all conditions**. This gives Logos its declarative character — you say what you want to know, not how to compute it.

## 3. The Principle: Facts Are Not Variables

This principle is the most important design decision in Logos, and the one that most distinguishes it from conventional languages.

In a conventional language:

```python
age = 30       # age is a variable
age = 31       # now age is 31; 30 is gone
```

In Logos:

```logos
age of alice := 30 years [source: "estimate-2025"]
age of alice := 31 years [source: "passport-2026"]
```

Both bindings exist simultaneously. They have different provenances. A query for `age of alice` returns both, with their confidences. An inference rule can choose the highest-confidence binding, the most recent, the one from the most trusted source, or can combine them.

This principle has several consequences:

1. **Logos programs are monotonic by default.** Asserting new facts never removes old ones. The knowledge base only grows. (Explicit retraction is possible but leaves a retraction record.)

2. **Reasoning is reproducible.** Given the same knowledge base, the same query always produces the same result. There is no mutable state that can cause nondeterminism.

3. **Historical reasoning is natural.** Because old facts are retained with timestamps, you can query "what did we believe about Alice's age in January 2025?" without special time-travel machinery.

4. **Debugging is tractable.** Every conclusion is backed by an explicit chain of bindings and rules. The runtime can explain any answer by traversing the dependency graph.

## 4. Confidence-First Design

Confidence is not an optional annotation in Logos — it is a structural component of every value. The "absolute" confidence (certainty) is a special case of the general confidence model, not the default assumption.

This has a profound implication for how programs are written. In conventional languages, the developer handles uncertainty through ad hoc mechanisms: nullable fields, error types, exception hierarchies, out-of-band logging. In Logos, uncertainty is expressed directly in the language:

```logos
// Certain fact
capital of France := "Paris"

// Uncertain fact with point estimate
population of France := 67_000_000 [confidence: 0.90]

// Uncertain fact with full distribution
gdp-growth-rate of France := 1.2% [
  confidence: { estimate: 0.75, ci95: [0.60, 0.88], distribution: "Beta" }
  source: "IMF projection 2026"
]
```

When rules derive conclusions from uncertain facts, the uncertainty propagates automatically. The developer never writes confidence-bookkeeping code; it happens in the inference engine.

## 5. The Semantic Graph as Universal Runtime Structure

Every Logos runtime maintains a single, unified **semantic graph** — a labeled, directed, typed multigraph where:

- **Nodes** are entities, values, and rules.
- **Edges** are labeled with field/predicate names.
- **Edge metadata** carries confidence, provenance, and timestamps.
- **Rule nodes** are connected to their premises and conclusions.

This graph is the only runtime structure. There are no separate heaps, stacks, or symbol tables. The graph is:

- **Persistent** — it survives across queries and can be serialized.
- **Inspectable** — any node or edge can be queried directly.
- **Reactive** — changes to any node automatically propagate to dependent nodes.
- **Distributable** — the graph can be partitioned across machines; edges can span partitions.

The dependency subgraph for any derived fact is always available and can be rendered as a visual explanation of how that fact was derived:

```
can-vote(alice)
  ← age of alice >= 18 years
      ← age of alice = 30 years [source: passport]
  ← nationality of alice = "American"
      ← nationality of alice = "American" [source: census]
```

## 6. Self-Hosting

Logos is designed to be self-hosting in a specific sense: the Logos type system and inference rules for Logos itself are expressible in Logos. The meta-level description of what constitutes a valid Logos program is a Logos knowledge base.

This means:

- Type checking is performed by inference rules over the type lattice.
- The IS-A lattice itself is a Logos knowledge base.
- A Logos runtime can introspect its own rule set.
- AI systems reasoning about Logos programs can use Logos to represent their understanding.

The self-hosting architecture is not merely a philosophical commitment — it has practical consequences for language tooling. A Logos-aware editor, linter, or documentation generator can itself be written in Logos, querying the Logos meta-knowledge-base to understand program structure.

## 7. The Name

"Logos" (λόγος) is the ancient Greek word for word, reason, plan, and discourse. Aristotle used it as a mode of persuasion through logic and reasoned argument. In philosophy of language it represents the rational structure of reality as expressible through language. In Logos the programming language, these meanings converge: the language is simultaneously a representation of knowledge, a system of reasoning, and a medium of communication between human and artificial minds.
