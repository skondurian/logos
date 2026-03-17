# Logos Language Specification — Chapter 4: Semantic Bindings

## 1. Introduction

A **semantic binding** is the fundamental unit of knowledge assertion in Logos. Where a conventional language says "assign value V to variable X," Logos says "assert that the field F of entity E has value V, with the following provenance."

The distinction is not merely syntactic. A semantic binding:

- Is **immutable** after assertion (it cannot be changed, only retracted).
- Carries **provenance** (source, timestamp, asserting agent).
- Carries **confidence** (a probability distribution over its truth).
- Coexists with **contradicting bindings** rather than overwriting them.
- Is a **node in the semantic graph**, not a slot in a symbol table.

## 2. Binding Syntax

### 2.1 Basic Binding

```
Binding ::= SubjectPredicate ':=' Value AnnotationBlock? NEWLINE

SubjectPredicate ::= FieldName 'of' EntityRef
                   | EntityRef '.' FieldName   // dot form (alternative)

Value ::= Literal | EntityRef | RecordLiteral | ListLiteral | SetLiteral | Expression

AnnotationBlock ::= '[' NEWLINE? Annotation+ ']'

Annotation ::= AnnotationKey ':' AnnotationValue NEWLINE?
AnnotationKey ::= 'confidence' | 'source' | 'asserted-at' | 'asserted-by' | identifier
```

### 2.2 Examples

**Simplest form — no annotations:**

```logos
age of alice := 30 years
nationality of alice := "American"
employer of alice := acme-corp
```

**With confidence:**

```logos
age of alice := 30 years [confidence: 0.95]
```

**With full provenance:**

```logos
age of alice := 30 years [
  confidence: 0.95
  source: "DMV database"
  asserted-at: @2026-01-15
  asserted-by: data-import-agent
]
```

**Dot form (alternative syntax):**

```logos
alice.age := 30 years
alice.nationality := "American"
```

The `field of entity` form is preferred because it reads more naturally as an English statement. The dot form is provided for familiarity and is semantically equivalent.

## 3. How Bindings Differ from Variable Assignment

The following table makes the contrast explicit:

| Property | Variable Assignment (Python) | Semantic Binding (Logos) |
|----------|------------------------------|--------------------------|
| Mutability | Mutable (overwrite at will) | Immutable (retract explicitly) |
| History | Destroyed on overwrite | All historical bindings retained |
| Semantics | Memory location | Fact in a knowledge graph |
| Provenance | None | Mandatory (defaults available) |
| Confidence | Not applicable | Mandatory (defaults to absolute) |
| Conflict | Last write wins | Both facts coexist |
| Queryable | Only current value | All values, with filter by provenance |
| Typed | Optional | Checked against ontological type |
| Observable | By running code | By querying the graph |

### 3.1 The Immutability Principle

Once asserted, a binding cannot be changed. The identity of a binding is determined by the triple `(subject, predicate, provenance-id)` — not by `(subject, predicate)` alone. This means:

```logos
// These are TWO SEPARATE BINDINGS, not an overwrite
age of alice := 28 years [source: "estimate-2024", asserted-at: @2024-06-01]
age of alice := 30 years [source: "passport-2026",  asserted-at: @2026-01-15]
```

Both bindings exist in the knowledge graph simultaneously. A query `find age of alice` returns both:

```
age of alice:
  28 years  [confidence: absolute, source: "estimate-2024", asserted-at: 2024-06-01]
  30 years  [confidence: absolute, source: "passport-2026", asserted-at: 2026-01-15]
```

The inference engine resolves conflicts using confidence and recency when needed (see Section 7).

## 4. Provenance Record Structure

Every binding carries a **provenance record** — a structured object describing the origin of the binding. The full structure is:

```logos
type ProvenanceRecord IS-A Entity
  fields:
    source: Text?           // description or name of the source
    asserted-at: DateTime?  // when the binding was asserted
    asserted-by: Entity?    // who/what asserted the binding
    derived-from: [Binding] // for inferred bindings: the premises used
    rule-applied: Rule?     // for inferred bindings: the rule that fired
    retracted: Boolean      // true if this binding has been retracted
    retracted-at: DateTime? // when it was retracted
    retracted-by: Entity?   // who retracted it
```

### 4.1 Default Provenance

When no annotation block is supplied, provenance defaults are:

| Field | Default |
|-------|---------|
| `confidence` | `absolute` (Dirac delta at 1.0) |
| `source` | `"[unspecified]"` |
| `asserted-at` | Current system time at parse/load time |
| `asserted-by` | `[current-agent]` (the loading process) |

### 4.2 Derived Bindings

When an inference rule derives a new fact, the runtime automatically constructs a provenance record:

```logos
can-vote(alice)
  // Derived provenance:
  // derived-from: [age of alice, nationality of alice]
  // rule-applied: can-vote-rule
  // asserted-at: [time of inference]
  // confidence: <product of premise confidences>
```

Derived bindings are **not stored** unless explicitly cached (see Section 8). The runtime re-derives them on each query unless caching is enabled.

## 5. Confidence Annotation

Confidence values in binding annotations may take several forms. Full details are in Chapter 5; this section covers the syntactic forms.

### 5.1 Absolute (Certain)

```logos
capital of France := "Paris"
// confidence defaults to absolute

capital of France := "Paris" [confidence: absolute]
// explicit absolute
```

### 5.2 Point Estimate

```logos
age of alice := 30 years [confidence: 0.95]
```

### 5.3 Full Distribution

```logos
age of alice := 30 years [
  confidence: {
    estimate: 0.95
    ci95: [0.88, 0.99]
    distribution: "Beta"
  }
]
```

### 5.4 Named Confidence Levels

As a convenience, named confidence levels may be used:

| Name | Numeric Equivalent |
|------|-------------------|
| `absolute` | 1.0 (Dirac delta) |
| `certain` | 0.99 |
| `high` | 0.85 |
| `medium` | 0.65 |
| `low` | 0.40 |
| `speculative` | 0.20 |

```logos
age of alice := 30 years [confidence: high]
```

Named levels are syntactic sugar; they are converted to numeric values immediately.

## 6. Binding Scopes

### 6.1 Global Scope

Bindings declared at the top level of a Logos file are in the **global scope** of that file's namespace. They are visible to all rules and queries within the file and to importing modules.

### 6.2 Local Scope (Query-Scoped Bindings)

Bindings created during query evaluation — intermediate results, variable bindings during rule resolution — exist in a **query scope** that is destroyed when the query completes. These are not persisted to the knowledge graph unless explicitly requested with a `cache` directive.

### 6.3 Rule-Scoped Variables

Variables introduced in inference rule conditions (uppercase identifiers) are scoped to the rule body. They are unified during proof search and do not persist after the rule fires.

```logos
can-vote(P) if:
  age of P >= 18 years      // P is bound during unification
  nationality of P == "American"  // same P
// P is no longer in scope after this rule
```

## 7. Contradiction Handling

When two bindings assert different values for the same `(subject, predicate)` pair, a **contradiction** exists. Logos does not treat this as an error. Both bindings are retained with their respective provenances.

### 7.1 Contradiction Detection

The runtime detects contradictions when:

- Two bindings have the same subject and predicate.
- Their values are incompatible (different scalars, non-overlapping ranges).

Bindings with overlapping value ranges (e.g., age = 30 and age = 31) are flagged as potential contradictions but not definite ones.

### 7.2 Contradiction Resolution Strategies

The runtime supports several resolution strategies, selectable per-query:

**Most-confident first (default):**
When a rule needs a single value for a field and multiple bindings exist, the binding with the highest confidence is used. Others are available as alternatives.

```logos
// Rule uses the highest-confidence age binding
can-vote(P) if:
  age of P >= 18 years
  // If P has two age bindings (0.9 and 0.7), uses the 0.9 one first
```

**Most-recent first:**
The binding with the latest `asserted-at` timestamp is preferred.

**Trusted-source first:**
The binding from the source with the highest declared trust level is preferred.

**All-paths:**
The rule is evaluated once for each binding, producing multiple conclusions with distinct confidences.

### 7.3 Contradiction Record

When a contradiction is detected, the runtime creates a **contradiction record** in the knowledge graph:

```logos
type ContradictionRecord IS-A Entity
  fields:
    subject: Entity
    predicate: Text
    binding-a: Binding
    binding-b: Binding
    detected-at: DateTime
    resolution: Text?
```

This record is itself queryable: `find all ContradictionRecord` returns all known contradictions.

### 7.4 Example

```logos
age of alice := 28 years [source: "HR system",   confidence: 0.7]
age of alice := 30 years [source: "passport",     confidence: 0.95]

// Query: is alice old enough to vote?
// The runtime uses the highest-confidence binding (30 years, 0.95)
// and derives: can-vote(alice) [confidence: 0.95]
// The 28-year binding is not discarded; it affects the contradiction record.
```

## 8. Retraction

A binding can be **retracted** using the `retract` statement. Retraction does not delete the binding; it marks it as retracted in the provenance record.

### 8.1 Retraction Syntax

```
RetractStmt ::= 'retract' ':' SubjectPredicate NEWLINE
              | 'retract' ':' SubjectPredicate '[' RetractAnnotation+ ']' NEWLINE

RetractAnnotation ::= 'source' ':' Text
                    | 'reason' ':' Text
                    | 'retracted-by' ':' EntityRef
```

### 8.2 Simple Retraction

```logos
retract: age of alice
```

This retracts **all** bindings for `age of alice`. If there are multiple bindings (from different sources), all are retracted.

### 8.3 Targeted Retraction

To retract only the binding from a specific source:

```logos
retract: age of alice [source: "HR system"]
```

Only the binding where `provenance.source == "HR system"` is retracted. The binding from `"passport"` remains active.

### 8.4 Retraction Effects

When a binding is retracted:

1. The binding's provenance record is updated: `retracted := true`, `retracted-at := now`.
2. All **derived facts** that depended on this binding are **automatically invalidated**.
3. If an alternative binding exists for the same `(subject, predicate)`, the runtime may re-derive facts using the alternative.
4. The retraction itself is a fact in the knowledge graph (the retraction record is permanent).

### 8.5 Retraction Record

```logos
// After: retract: age of alice [source: "HR system"]
// The knowledge graph contains:
//
// age of alice := 28 years [
//   source: "HR system"
//   confidence: 0.7
//   retracted: true
//   retracted-at: @2026-03-16T09:15:00Z
// ]
```

Retracted bindings are excluded from query results by default. To include them:

```logos
find age of alice [include-retracted: true]
```

## 9. Multi-Valued Fields

Some fields are naturally multi-valued: a person may have multiple phone numbers, a document may have multiple authors. Logos handles this through repeated bindings and through the `List` and `Set` types.

### 9.1 Repeated Bindings (Multi-fact)

```logos
phone of alice := "+1-555-0100" [label: "mobile"]
phone of alice := "+1-555-0101" [label: "office"]
```

Both bindings are active. `find phone of alice` returns both. This is the recommended approach for sets of facts that are semantically parallel.

### 9.2 List Binding (Single-fact, ordered)

```logos
phone-numbers of alice := ["+1-555-0100", "+1-555-0101"]
```

A single binding whose value is a list. Appropriate when order matters or when the list is managed as a unit.

### 9.3 Set Binding (Single-fact, unordered)

```logos
permissions of alice := #{"read", "write", "admin"}
```

## 10. Binding Queries

The `find` form queries bindings from the knowledge graph. Full query semantics are defined in Chapter 7; here we cover binding-specific queries.

### 10.1 Field Query

```logos
find age of alice
```

Returns all active bindings for `age of alice`, with their confidences and provenances.

### 10.2 Provenance Query

```logos
find source of (age of alice)
find asserted-at of (age of alice)
```

The provenance fields of a binding are themselves queryable using the same `field of (binding)` syntax.

### 10.3 Pattern Query

```logos
find age of P where P :: Person
```

Returns all `(P, age)` pairs where P is a Person.

### 10.4 Confidence-Filtered Query

```logos
find age of alice [min-confidence: 0.9]
```

Returns only bindings with confidence ≥ 0.9.

## 11. Syntactic Sugar: Inline Type Ascription

A common pattern is to declare an entity's type alongside its first binding:

```logos
// Verbose form
alice :: Person
name of alice := { first: "Alice", last: "Smith" }
age of alice := 30 years

// Inline type ascription (syntactic sugar)
alice [:: Person]:
  name := { first: "Alice", last: "Smith" }
  age := 30 years
```

In the inline form, `name` and `age` are understood to refer to the fields of the declared type. This is sugar for the explicit `field of entity` form.

## 12. Binding Uniqueness and Identity

Each binding has a unique **binding ID** — an opaque identifier generated by the runtime at assertion time. This ID is used in provenance records to refer to specific bindings.

```logos
// The runtime assigns an ID, e.g.: binding#a3f8c2
age of alice := 30 years [source: "passport"]

// Later, can refer to this binding by ID in retraction or contradiction resolution
retract: binding#a3f8c2
```

Binding IDs are stable across serialization/deserialization of the knowledge graph.
