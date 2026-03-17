# 08 — Contexts

## Overview

A **context** is a named configuration envelope that governs how the semantic graph is queried and how inference results are evaluated. Contexts control the confidence threshold below which facts are treated as absent, the tolerance for contradictions, and the subset of facts that are visible to queries. They are the mechanism by which a single Logos program can behave differently in production versus staging versus testing, or across jurisdictions that impose different rules.

---

## Declaration Syntax

```logos
context <name> :
    confidence-threshold : <number 0.0–1.0>
    error-tolerance      : <level>           // strict | lenient | permissive
    visible-fact-tags    : [<tag>, ...]      // optional whitelist
    hidden-fact-tags     : [<tag>, ...]      // optional blacklist
    <additional settings>
```

Example:

```logos
context Production :
    confidence-threshold : 0.85
    error-tolerance      : strict

context Staging :
    confidence-threshold : 0.65
    error-tolerance      : lenient

context Testing :
    confidence-threshold : 0.50
    error-tolerance      : permissive
    hidden-fact-tags     : [external-data]
```

---

## Confidence Threshold

The `confidence-threshold` setting is the floor below which any inferred or asserted fact is treated as **absent** within that context. A fact with confidence 0.70 is visible in `Testing` (threshold 0.50) but invisible in `Production` (threshold 0.85).

This allows the same base rules and facts to produce different query results depending on operational requirements. In production you want high certainty; in testing you want to see candidate facts that are still being refined.

```logos
context HighAssurance :
    confidence-threshold : 0.95

context Research :
    confidence-threshold : 0.30
```

Within `HighAssurance`, a query `find P where can-vote(P)` returns only persons for whom `can-vote` is inferred with confidence >= 0.95. Within `Research`, the same query returns anyone for whom there is at least weak evidence.

---

## Error Tolerance Levels

| Level         | Behavior                                                                                  |
|---------------|-------------------------------------------------------------------------------------------|
| `strict`      | Any contradiction among visible facts raises a `ContradictionError` and halts inference   |
| `lenient`     | Contradictions are logged; the higher-confidence fact wins; inference continues            |
| `permissive`  | Contradictions are silently resolved by recency; no error is raised                       |

```logos
context AuditableDecisions :
    confidence-threshold : 0.90
    error-tolerance      : strict    // any contradiction must be investigated
```

---

## Context Inheritance

A context may extend another context, inheriting all its settings and overriding specific ones:

```logos
context Base :
    confidence-threshold : 0.70
    error-tolerance      : lenient

context EU extends Base :
    confidence-threshold : 0.80     // override
    visible-fact-tags    : [gdpr-compliant]

context US extends Base :
    hidden-fact-tags     : [eu-only]
```

Inheritance is single: a context extends at most one parent. Settings not overridden are inherited verbatim. The `Base` context is implicitly extended by all user-defined contexts that do not name a parent, unless a default is declared (see Default Context).

---

## Activating a Context

Use the `within` block to execute queries and transforms under a specific context:

```logos
within Production :
    let result = find P where can-vote(P)
    assert AuditLog : query = "can-vote", result-count = count(result)
```

The `within` block is lexically scoped. Any query, transform invocation, or assertion inside the block runs under the named context. Nested `within` blocks replace the active context for their scope:

```logos
within Production :
    let prod-result = find P where eligible(P)

    within Staging :
        let staging-result = find P where eligible(P)
        // uses Staging thresholds
    // back to Production here
```

---

## Default Context

Every Logos program has an implicit **default context** named `Default`:

```logos
context Default :
    confidence-threshold : 0.50
    error-tolerance      : lenient
```

Programs that do not declare any context or use any `within` block run under `Default`. The program may override `Default` by declaring a context with that name:

```logos
context Default :
    confidence-threshold : 0.75
    error-tolerance      : strict
```

This changes the baseline for the entire program. It is good practice to declare an explicit `Default` so behavior is unambiguous.

---

## How Contexts Filter Facts

When a context becomes active, the executor applies two filters to the semantic graph:

1. **Tag filter** — facts tagged with a tag in `hidden-fact-tags` are excluded from the visible subgraph. Facts tagged with a tag in `visible-fact-tags` (if the list is non-empty) are included; all others are excluded.

2. **Confidence filter** — facts with a confidence score below `confidence-threshold` are excluded.

The filtered subgraph is what inference and queries operate on. Facts outside the filtered subgraph do not participate in rule firing or unification.

```logos
assert PersonFact : name = "Alice", age = 30
    tags : [verified, gdpr-compliant]

assert PersonFact : name = "Bob", age = 25
    tags : [unverified]

context EU extends Base :
    visible-fact-tags : [gdpr-compliant]
```

Within `EU`, only Alice's fact is visible. Queries for Bob return no results.

---

## Context-Sensitive Queries

Queries are always evaluated against the active context. The result type carries the context name in its provenance:

```logos
within Production :
    let voters = find P where can-vote(P)
    // voters.provenance.context = "Production"
```

A single query variable may be resolved in multiple contexts for comparison:

```logos
let prod-voters    = within Production : find P where can-vote(P)
let staging-voters = within Staging    : find P where can-vote(P)
let diff = prod-voters difference staging-voters
```

---

## Multiple Active Contexts

At any point in execution, exactly one context is active (the innermost `within` scope). There is no concept of simultaneously active contexts for a single query; however, a program may merge results from queries run under different contexts:

```logos
let conservative = within HighAssurance : find P where eligible(P)
let liberal      = within Research      : find P where eligible(P)

let agreed-set   = conservative intersection liberal
let uncertain    = liberal difference conservative
```

This pattern is useful for identifying facts that are borderline — visible in a lenient context but not in a strict one.

---

## Context Merge Semantics on Import

When a module is imported, its context declarations are merged into the importing program's context namespace. If two modules declare a context with the same name, the rules are:

1. If the declarations are identical, they merge without conflict.
2. If the declarations differ, the importing program's declaration takes precedence, and a `ContextConflictWarning` is emitted at load time.
3. If neither module is the importer (both are library modules), a `ContextConflictError` is raised.

```logos
import voting from rules.logos     // declares context Production
import payments from finance.logos // declares context Production (different settings)
// Warning: ContextConflictWarning on "Production"; importer's definition wins
```

To avoid conflicts, library modules should use namespaced context names:

```logos
context voting.Production :
    confidence-threshold : 0.90
```

---

## Practical Patterns

### Environment-Gated Assertions

```logos
context Production :
    confidence-threshold : 0.85
    error-tolerance      : strict

context Development :
    confidence-threshold : 0.40
    error-tolerance      : permissive

// assert a test fact only visible in Development
assert TestPersonFact : name = "TestUser", age = 20
    tags : [dev-only]

context Development :
    visible-fact-tags : [dev-only]
```

### Jurisdictional Contexts

```logos
context EU extends Base :
    confidence-threshold : 0.80
    visible-fact-tags    : [gdpr-compliant]
    hidden-fact-tags     : [us-only]

context US extends Base :
    confidence-threshold : 0.75
    hidden-fact-tags     : [eu-only]

transform eligible-for-service [user: Person, jurisdiction: Jurisdiction] → Boolean :
    intent : "Determine if a user is eligible under the applicable legal context"
    within jurisdiction.context :
        result = can-use-service(user) = true
```

### Progressive Confidence Degradation

```logos
context Realtime :
    confidence-threshold : 0.90

context Batch :
    confidence-threshold : 0.70

context Archive :
    confidence-threshold : 0.40
```

Higher thresholds in real-time contexts ensure only well-supported facts drive live decisions; lower thresholds in archival contexts allow historical analysis of weaker evidence.

---

## Summary

- Contexts are named configuration envelopes that adjust confidence thresholds, error tolerance, and fact visibility.
- They are declared with `context Name :` and activated with `within Name :` blocks.
- Contexts support single inheritance via `extends`.
- Fact filtering is two-dimensional: by tag whitelist/blacklist and by confidence threshold.
- Exactly one context is active at any point; multiple contexts can be composed by running separate queries and merging results.
- Imported context declarations merge into the global namespace with importing-program precedence.
