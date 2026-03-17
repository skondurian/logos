# 07 — Transforms

> **Implementation Status:** Transform declarations are parsed by the runtime, but transform invocation (execution) is **not yet implemented**. The transform body is not evaluated. This chapter describes the intended design. Syntax and semantics described here are subject to change as the executor is built.

## Overview

A **transform** is a declarative, function-like construct that specifies *what* a computation should produce and under what constraints, without prescribing *how* to produce it. When implemented, the executor will convert a transform invocation into an inference problem and resolve it against the current semantic graph.

Transforms differ from functions in a conventional language in a fundamental way: a function is a procedure that runs deterministically and returns a value. A transform is a specification of a desired output, annotated with intent, constraints, and optimization objectives. The executor is free to choose any inference strategy that satisfies those constraints.

---

## Declaration Syntax

```logos
transform <name> [<parameter-list>] → <return-type> :
    intent      : <natural-language description>
    constraints : <constraint-block>
    optimize    : <objective>              // optional
    confidence  : <minimum threshold>     // optional
    <body>
```

The body of a transform is a set of **declarative clauses** — logical assertions, pattern matches, and conditional expressions that constrain the solution space. The executor does not execute the body top-to-bottom; it uses the clauses as inference rules.

---

## Minimal Example

```logos
transform recommend [user: Person] → Set<Product> :
    intent     : "Return products the user is likely to want"
    confidence : 0.75

    let interests = user.interests
    let candidates = Product where category member-of interests
    result member-of candidates
    result.available = true
```

The executor resolves `result` by finding all `Product` instances that satisfy the constraints. The `confidence : 0.75` clause requires every element of the returned set to carry a confidence score of at least 0.75, derived from the provenance chain of the inference.

---

## Parameter List

Parameters are typed bindings. They are treated as ground facts injected into the semantic graph for the duration of the transform resolution.

```logos
transform can-travel [traveler: Person, destination: Country] → Boolean :
    intent : "Determine whether the traveler may legally enter the destination"
    traveler.passport.valid = true
    not destination.entry-banned(traveler.nationality)
    traveler.age >= destination.minimum-entry-age
```

Parameters may carry default values:

```logos
transform preferred-language [user: Person, fallback: Language = English] → Language :
    intent : "Resolve the user's preferred language"
    result = user.language or fallback
```

---

## Return Types

A transform may return any Logos type:

| Return type      | Meaning                                           |
|------------------|---------------------------------------------------|
| `Boolean`        | Satisfiability check                              |
| `T`              | Single value of type T                            |
| `Set<T>`         | All solutions of type T satisfying constraints    |
| `Relation<T, U>` | All satisfying pairs                              |
| `Maybe<T>`       | Single solution or absent                         |
| `Ranked<T>`      | Solutions ordered by the optimization objective   |

---

## Intent Annotation

The `intent` field is a required natural-language string. It serves three purposes:

1. **Documentation** — human-readable explanation of the transform's purpose.
2. **Executor hint** — the executor may use the intent string to select among multiple applicable inference strategies.
3. **Audit trail** — the intent is recorded in the provenance chain of every fact derived by the transform.

```logos
transform age-group [person: Person] → AgeGroup :
    intent : "Classify a person into a demographic age group for analytics"
    person.age < 18  → result = Minor
    person.age < 65  → result = Adult
    person.age >= 65 → result = Senior
```

Intent strings are not evaluated by the type-checker, but a linter may warn when the intent is absent or fewer than ten characters.

---

## Constraint Specification

Constraints are logical clauses that the result must satisfy. Any clause in the transform body that references `result` is treated as a constraint on the output.

```logos
transform affordable-hotels [city: City, budget: Money] → Set<Hotel> :
    intent      : "Find hotels in a city within a price budget"
    constraints :
        result.city    = city
        result.price   <= budget
        result.rating  >= 3.0
        result.open    = true
```

The `constraints` keyword is syntactic sugar; plain body clauses are equivalent. The keyword block groups them for readability and is recommended when there are more than three constraints.

Constraints compose with `and`, `or`, and `not`:

```logos
    constraints :
        result.city = city
        and (result.price <= budget or result.member-rate = true)
        and not result.closed-for-renovation
```

---

## Optimization Objectives

An `optimize` clause directs the executor to prefer solutions that maximize or minimize an expression:

```logos
optimize : maximize result.user-rating
optimize : minimize result.price
optimize : maximize result.relevance-score - (result.distance * 0.1)
```

When combined with a `Set<T>` return type, `optimize` produces a `Ranked<T>` result that can be truncated to a top-N slice:

```logos
transform top-restaurants [city: City, n: Integer = 10] → Ranked<Restaurant> :
    intent   : "Return the top-N restaurants in a city by composite score"
    optimize : maximize (result.rating * 0.6 + result.popularity * 0.4)
    result.city = city
    result.open = true
```

Callers may request a specific number of results:

```logos
let dinner-spots = top-restaurants[city: London] take 5
```

---

## Confidence Requirements

```logos
confidence : <expression>
```

The confidence clause sets a **minimum acceptable confidence** for the transform's result. The executor will not include any candidate in the result whose inferred confidence falls below this threshold.

```logos
transform is-fraudulent [transaction: Transaction] → Boolean :
    intent     : "Flag transactions that are likely fraudulent"
    confidence : 0.90
    transaction.amount > transaction.account.usual-max * 3
    or transaction.location far-from transaction.account.home-location
    or transaction.time within unusual-hours
```

If no candidate meets the confidence threshold, the transform returns `absent` (for `Maybe<T>`) or an empty set (for `Set<T>`).

Confidence may also be expressed as a named level:

```logos
confidence : high    // equivalent to 0.85
confidence : medium  // equivalent to 0.65
confidence : low     // equivalent to 0.40
```

---

## How Transforms Differ from Functions

| Aspect              | Function (procedural)           | Transform (declarative)                     |
|---------------------|---------------------------------|---------------------------------------------|
| Body semantics      | Sequence of statements          | Set of constraints / inference rules        |
| Execution model     | Call stack                      | Inference engine resolution                 |
| Return value        | Computed deterministically      | Derived from semantic graph                 |
| Failure mode        | Exception / error               | Absent / empty / low-confidence result      |
| Optimization        | Manual loop                     | Declared objective, executor decides how    |
| Provenance          | None                            | Full derivation chain attached to result    |
| Side effects        | Permitted                       | Forbidden; transforms are pure              |

Transforms cannot perform IO, mutate facts, or call procedures with side effects. They are referentially transparent with respect to the semantic graph at the time of resolution.

---

## Transform Composition

A transform may reference another transform in its body:

```logos
transform eligible-destinations [traveler: Person] → Set<Country> :
    intent : "Countries the traveler can legally visit"
    can-travel[traveler: traveler, destination: result] = true

transform vacation-options [traveler: Person] → Set<Hotel> :
    intent : "Hotels the traveler can reach and afford"
    let destinations = eligible-destinations[traveler: traveler]
    result.country member-of destinations
    result.price <= traveler.budget
```

When the executor resolves `vacation-options`, it first resolves `eligible-destinations` and treats its result as a fact set. The provenance chain of the inner result is threaded into the outer result's provenance.

Recursive transform composition is permitted if the recursion is well-founded (i.e., terminates on the finite semantic graph). The executor detects non-terminating recursion and raises a `CycleError` at resolution time.

---

## How the Executor Resolves a Transform

1. **Grounding** — bind parameters to concrete values from the semantic graph.
2. **Clause compilation** — convert each constraint clause into a logical formula over the graph.
3. **Unification** — find all assignments to `result` that satisfy all formulae simultaneously.
4. **Confidence scoring** — compute a confidence value for each candidate from the provenance of the facts used.
5. **Filtering** — discard candidates below the declared confidence threshold.
6. **Ranking** — if an `optimize` clause is present, sort candidates by the objective expression.
7. **Return** — wrap the result set with provenance metadata and return to the caller.

The executor may use any sound inference strategy (backward chaining, forward chaining, constraint propagation, SMT solving) as long as the result is semantically equivalent to exhaustive search over the graph.

---

## Full Example: Product Recommendation

```logos
transform recommend [user: Person] → Ranked<Product> :
    intent      : "Return products the user is likely to buy, ranked by predicted affinity"
    confidence  : 0.70
    optimize    : maximize result.predicted-affinity(user)
    constraints :
        result.available         = true
        result.region-compatible = user.region
        not result member-of user.purchase-history
        result.category member-of user.interests
            or result.category member-of user.browsed-categories

let alice-picks = recommend[user: alice] take 10

for product in alice-picks :
    assert Recommendation :
        user    = alice
        product = product
        score   = product.predicted-affinity(alice)
        basis   = product.provenance
```

---

## Summary

- Transforms are declarative specifications of desired outputs, not procedures.
- They carry intent, constraints, optimization objectives, and confidence requirements.
- The executor converts a transform into an inference problem and resolves it against the semantic graph.
- Transforms compose by referencing each other; provenance threads through the composition chain.
- Results carry full provenance, enabling audit and explanation.
