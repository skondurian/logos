# 10 — Queries

## Overview

Queries are the primary mechanism for extracting information from the semantic graph. A query is a declarative expression that specifies a pattern to match against inferred and asserted facts, optionally filtered by confidence, annotated with provenance requirements, and optionally aggregated into summary statistics. Every query result carries a value, a confidence score, and a full provenance chain.

---

## Query Forms

Logos provides four primary query forms:

| Form                                    | Returns                          |
|-----------------------------------------|----------------------------------|
| `query: can-vote(alice)?`               | Boolean + confidence             |
| `find P where can-vote(P)`              | Set of bindings + provenance     |
| `find P, Q where knows(P, Q)`           | Relation (set of tuples)         |
| `find P where can-vote(P) confidence > 0.8` | Filtered set                 |

---

## Boolean Queries

A boolean query asks whether a specific ground fact holds:

```logos
query: can-vote(alice)?
```

Return type: `QueryResult<Boolean>`

```logos
QueryResult {
    value      : true
    confidence : 0.92
    provenance : [
        alice.age   → asserted at main.logos:12
        voting-age  → asserted at rules.logos:5
        age-check   → rule fired at rules.logos:10
    ]
}
```

Boolean queries can be used in conditional expressions:

```logos
if (query: can-vote(alice)?) .value = true :
    assert VoterRegistration : person = alice
```

The `.value` and `.confidence` fields are always accessible on a `QueryResult`.

### Negation in Boolean Queries

```logos
query: not can-vote(bob)?
```

Returns `true` if `can-vote(bob)` is not derivable (closed-world assumption). The confidence of a negated result is the complement of the positive derivability confidence, or 1.0 if the positive fact is entirely absent from the graph.

---

## Set Queries: `find P where`

A set query binds a variable and returns all ground values for which the pattern holds:

```logos
find P where can-vote(P)
```

Return type: `Set<QueryResult<Person>>`

Each element of the set is a `QueryResult` carrying the binding, confidence, and provenance for that specific derivation.

```logos
let voters = find P where can-vote(P)

for voter in voters :
    print voter.value.name, voter.confidence
```

Multiple conditions are conjoined with `and` or newline-continuation:

```logos
find P where
    can-vote(P)
    and P.age < 30
    and P.city = "Portland"
```

Conditions may reference derived predicates, transforms, and nested patterns:

```logos
find P where
    eligible(P)
    and (query: passed-background-check(P)?) .confidence > 0.85
```

---

## Relation Queries: `find P, Q where`

A relation query binds multiple variables and returns all satisfying tuples:

```logos
find P, Q where knows(P, Q)
```

Return type: `Relation<QueryResult<Person>, QueryResult<Person>>`

The result is a set of pairs `(P, Q)` where `knows(P, Q)` holds. Each pair carries a per-tuple confidence (the minimum of the two binding confidences, combined with the predicate confidence).

```logos
let social-graph = find P, Q where knows(P, Q)

for (person, acquaintance) in social-graph :
    print person.value.name, "knows", acquaintance.value.name
```

Three-way and higher-arity relations:

```logos
find P, Q, R where
    knows(P, Q)
    and knows(Q, R)
    and not knows(P, R)
```

This finds all "friend-of-a-friend" pairs where no direct connection exists.

---

## Confidence-Filtered Queries

Any `find` query may include a `confidence` clause that filters results by their derived confidence:

```logos
find P where can-vote(P) confidence > 0.8
```

Only results whose provenance-derived confidence exceeds 0.8 are included. The threshold applies to the confidence of the full derivation for that binding, not any individual fact.

Threshold operators:

| Operator | Meaning                             |
|----------|-------------------------------------|
| `> N`    | confidence strictly greater than N  |
| `>= N`   | confidence at least N               |
| `< N`    | confidence strictly less than N     |
| `<= N`   | confidence at most N                |
| `= N`    | confidence exactly N (rare)         |

Named thresholds may be used instead of numeric literals:

```logos
find P where can-vote(P) confidence >= high
```

Named levels are resolved from the active context's definition:

```logos
context Production :
    confidence-threshold : 0.85
    confidence-levels :
        low    : 0.40
        medium : 0.65
        high   : 0.85
        certain: 0.99
```

Multiple conditions may include per-predicate confidence requirements:

```logos
find P where
    can-vote(P)          confidence > 0.80
    and employed(P)      confidence > 0.70
    and P.age < 35
```

---

## Query Result Structure

Every query result is a `QueryResult<T>`:

```logos
type QueryResult<T> :
    value      : T
    confidence : Float [0.0, 1.0]
    provenance : ProvenanceChain
    context    : ContextName
    timestamp  : Timestamp
```

The `ProvenanceChain` is an ordered list of `ProvenanceStep`:

```logos
type ProvenanceStep :
    fact-id    : NodeId
    fact-type  : LogosType
    source     : SourceRef       // file + line, or "asserted-externally"
    rule       : Maybe<RuleRef>  // the rule that derived this step, if any
    confidence : Float
```

The chain is ordered from base facts (index 0) to the final derivation (last index). This enables full audit trails:

```logos
let result = query: can-vote(alice)?

for step in result.provenance :
    print step.fact-type, "confidence:", step.confidence, "from:", step.source
```

### Accessing Result Fields

```logos
result.value       // the typed value
result.confidence  // derived confidence
result.provenance  // full chain
result.provenance.depth      // number of steps
result.provenance.weakest    // the step with the lowest confidence
result.provenance.sources    // list of distinct source files
```

---

## Streaming Results

For large result sets, queries may be evaluated lazily and results consumed as a stream:

```logos
stream P where can-vote(P) :
    print P.value.name
```

The `stream` keyword replaces `find`. Results are yielded one at a time in topological order (base-first) as the executor evaluates the graph. The stream terminates when all matching nodes have been emitted.

Streaming is useful when:
- The result set is too large to hold in memory.
- Processing can begin before the full set is known.
- The caller wants to stop early (e.g., after finding the first N results).

Early termination:

```logos
stream P where can-vote(P) take 5 :
    register(P.value)
```

Stops after yielding the first 5 results. The executor suspends evaluation when the take limit is reached.

### Stream Ordering

By default, streams emit results in topological order (the order in which the executor derives them). An explicit `order-by` clause imposes a sort:

```logos
stream P where can-vote(P)
    order-by P.value.age descending
    take 10 :
    print P.value.name
```

Ordering a stream requires buffering results until all are known, so `order-by` on a stream degrades to set semantics for the ordering phase.

---

## Aggregation

Query results may be aggregated before returning:

```logos
count(find P where can-vote(P))
// → Integer: number of eligible voters

sum(find P where employed(P) select P.value.salary)
// → Number: total payroll

average(find P where employed(P) select P.value.salary)
// → Number: mean salary

min(find P where employed(P) select P.value.salary)
max(find P where employed(P) select P.value.salary)
```

The `select` clause extracts a field from the binding before aggregation.

### Grouped Aggregation

```logos
group (find P where employed(P)) by P.value.department
    aggregate count
```

Returns a `Map<Department, Integer>` where each key is a department and the value is the count of employees in that department.

```logos
group (find P where employed(P)) by P.value.department
    aggregate average P.value.salary
```

Returns `Map<Department, Number>` — average salary by department.

### Confidence-Weighted Aggregation

Aggregation functions may optionally weight by confidence:

```logos
average(find P where employed(P) select P.value.salary) weighted-by confidence
```

Produces a confidence-weighted mean, where low-confidence facts contribute less to the aggregate. The aggregate result carries its own composite confidence score.

---

## Query Composition

Queries may be bound to names and composed:

```logos
let eligible-voters = find P where can-vote(P) confidence > 0.85
let young-voters    = find P where P.value.age < 30 and P member-of eligible-voters
let swing-district  = find P where P member-of young-voters and P.value.district = "D-7"
```

Each binding is a `Set<QueryResult<T>>`. Set operations are available:

```logos
let A = find P where condition-a(P)
let B = find P where condition-b(P)

let both    = A intersection B
let either  = A union B
let only-a  = A difference B
```

Set operations preserve provenance: the provenance of an intersection element includes the provenances of both contributing result sets.

---

## Querying Inside Transforms

Transforms may use query expressions in their bodies:

```logos
transform has-friend-who-votes [person: Person] → Boolean :
    intent : "True if any of the person's friends is eligible to vote"
    let friends = find Q where knows(person, Q)
    result = exists f in friends : (query: can-vote(f.value)?) .value = true
```

The `exists` keyword over a set returns `true` if any element satisfies the predicate.

---

## Error Cases

| Condition                             | Result                             |
|---------------------------------------|------------------------------------|
| No matching facts                     | Empty set / `absent` / `false`     |
| All matches below confidence threshold| Empty set (no error)               |
| Type mismatch in pattern              | `TypeError` at type-check time     |
| Unbound variable in result            | `UnboundVariableError` at load     |
| Query over retracted fact             | Empty / `false` (retracted = absent)|
| Circular query dependency             | `CycleError`                       |

---

## Full Example

```logos
assert Person : name = "Alice", age = 30, citizen = true
assert Person : name = "Bob",   age = 16, citizen = true
assert Person : name = "Carol", age = 25, citizen = false
assert VotingAge : value = 18

rule can-vote :
    if Person.age >= VotingAge.value and Person.citizen = true
    then can-vote(Person)

// Boolean query
let alice-votes = query: can-vote(alice)?
print "Alice can vote:", alice-votes.value, "confidence:", alice-votes.confidence

// Set query
let voters = find P where can-vote(P)
print "Eligible voters:", count(voters)

// Confidence-filtered
let certain-voters = find P where can-vote(P) confidence >= 0.90
print "High-confidence voters:", count(certain-voters)

// Relation query
let knows-facts = find P, Q where knows(P, Q)

// Aggregation
let avg-age = average(find P where can-vote(P) select P.value.age)
print "Average voter age:", avg-age

// Streaming
stream P where can-vote(P) order-by P.value.age ascending :
    print P.value.name, P.value.age
```

---

## Summary

- Logos provides boolean, set, relation, and confidence-filtered query forms.
- Every result carries a value, confidence score, and a full provenance chain.
- Streaming queries yield results lazily with optional `take` and `order-by` clauses.
- Aggregation supports `count`, `sum`, `average`, `min`, `max`, `group`, and confidence-weighted variants.
- Query results are first-class values that can be bound, composed with set operations, and passed to transforms.
- The active context's confidence threshold and tag filters apply to all queries within its scope.
