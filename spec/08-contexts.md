# 08 — Contexts

## Overview

A **context** is a named configuration envelope that governs how the semantic graph is queried and how inference results are evaluated. Contexts control the confidence threshold below which facts are treated as absent and the subset of facts that are tagged for a given deployment environment. They are the mechanism by which a single Logos program can behave differently in production versus staging versus testing, or across jurisdictions that impose different rules.

### Implementation Status (v0.1)

The context system is partially implemented. The following features work in the current runtime:

- Declaring contexts with `confidence-threshold` and `error-tolerance`
- Tagging individual facts with a `context:` annotation
- Threshold filtering during inference (wired up as of v0.1)

The following features are **planned but not yet implemented**:

- `within` block syntax for lexically scoped context activation
- Context inheritance (`extends`)
- `visible-fact-tags` / `hidden-fact-tags` whitelist/blacklist filtering
- Context merge semantics on module import

---

## Declaration Syntax

```logos
context <name>:
    confidence-threshold: <number 0.0–1.0>
    error-tolerance: <level>    // zero | low | medium | high
```

Example:

```logos
context Production:
    confidence-threshold: 0.99
    error-tolerance: zero

context Development:
    confidence-threshold: 0.50
    error-tolerance: high
```

---

## Confidence Threshold

The `confidence-threshold` setting is the floor below which any inferred or asserted fact is treated as **absent** within that context. A fact with confidence 0.70 is usable in `Development` (threshold 0.50) but not in `Production` (threshold 0.99).

This allows the same base rules and facts to produce different query results depending on operational requirements. In production you want high certainty; in development you want to see candidate facts that are still being refined.

```logos
context HighAssurance:
    confidence-threshold: 0.95

context Research:
    confidence-threshold: 0.30
```

Within `HighAssurance`, a query `find P where can-vote(P)` returns only persons for whom `can-vote` is inferred with confidence >= 0.95. Within `Research`, the same query returns anyone for whom there is at least weak evidence.

---

## Error Tolerance Levels

The `error-tolerance` setting controls how contradictions among visible facts are handled. The valid levels are:

| Level | Numeric Value | Behavior |
|-------|--------------|----------|
| `zero` | 0.0 | No tolerance for contradictions; errors are raised immediately |
| `low` | 0.1 | Minor contradictions are logged; significant ones raise errors |
| `medium` | 0.3 | Contradictions are logged; inference continues with the higher-confidence fact (default) |
| `high` | 0.7 | Contradictions are silently resolved; inference always continues |

```logos
context AuditableDecisions:
    confidence-threshold: 0.90
    error-tolerance: zero    // any contradiction must be investigated
```

---

## Context Inheritance

> **Planned (not yet implemented):** Context inheritance via `extends` is not yet supported in the runtime.

The intended syntax when implemented:

```logos
// Planned syntax:
context Base:
    confidence-threshold: 0.70
    error-tolerance: medium

context EU extends Base:
    confidence-threshold: 0.80

context US extends Base:
    confidence-threshold: 0.75
```

---

## Activating a Context

> **Planned (not yet implemented):** The `within` block for lexically scoped context activation is not yet implemented in the runtime.

The intended syntax when implemented:

```logos
// Planned syntax — not yet implemented:
within Production:
    let result = find P where can-vote(P)
```

In the current runtime, contexts are declared and facts are tagged with a context annotation, but there is no `within` block. The active context affects threshold filtering globally for a given query execution.

---

## Tagging Facts with a Context

Facts can be annotated with a `context:` tag to associate them with a specific context:

```logos
temperature of sensor-1 := 72.4
  confidence: 0.99
  provenance: "calibrated-sensor"
  context: Production

temperature of sensor-2 := 68.0
  confidence: 0.7
  provenance: "uncalibrated-sensor"
  context: Development
```

The `context:` annotation tags the fact for organizational and filtering purposes. Full tag-based whitelist/blacklist filtering (`visible-fact-tags` / `hidden-fact-tags`) is **planned but not yet implemented**.

---

## Default Context

Every Logos program has an implicit **default context** with the following settings:

```logos
context Default:
    confidence-threshold: 0.0
    error-tolerance: medium
```

Programs that do not declare any context run under these defaults. The program may override the defaults by declaring a context with the name `Default`:

```logos
context Default:
    confidence-threshold: 0.75
    error-tolerance: low
```

---

## How Contexts Filter Facts

When a context is active, the runtime applies a **confidence filter**: facts with a confidence score below `confidence-threshold` are excluded from inference and queries.

The filtered subgraph is what inference and queries operate on. Facts below the threshold do not participate in rule firing or unification.

> **Planned:** Tag-based filtering (`visible-fact-tags` / `hidden-fact-tags`) will add a second dimension of filtering. When implemented, the executor will apply both the confidence filter and the tag filter together.

---

## Practical Patterns

### Environment-Gated Facts

```logos
context Production:
    confidence-threshold: 0.85
    error-tolerance: zero

context Development:
    confidence-threshold: 0.40
    error-tolerance: high

// A test fact tagged for Development only
temperature of test-sensor := 55.0
  confidence: 0.6
  provenance: "synthetic"
  context: Development
```

### Jurisdictional Contexts

```logos
context EU:
    confidence-threshold: 0.80
    error-tolerance: low

context US:
    confidence-threshold: 0.75
    error-tolerance: medium
```

### Progressive Confidence Degradation

```logos
context Realtime:
    confidence-threshold: 0.90

context Batch:
    confidence-threshold: 0.70

context Archive:
    confidence-threshold: 0.40
```

Higher thresholds in real-time contexts ensure only well-supported facts drive live decisions; lower thresholds in archival contexts allow historical analysis of weaker evidence.

---

## Summary

- Contexts are named configuration envelopes that adjust confidence thresholds and error tolerance.
- They are declared with `context Name:` and activated globally for a query execution.
- Error tolerance uses the levels `zero`, `low`, `medium`, and `high`.
- Facts can be tagged with a `context:` annotation for organizational purposes.
- The default context has threshold 0.0 and `medium` error tolerance.
- Context inheritance (`extends`), `within` blocks, and tag-based whitelist/blacklist filtering are planned for a future version.
