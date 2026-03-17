# 09 — Dependency-Graph Execution Model

## Overview

Logos programs do not execute imperatively. Instead, every fact, derived fact, and query result exists as a node in a **SemanticGraph** — a directed acyclic graph (DAG) of FactNodes connected by dependency edges. The executor materializes this graph, computes nodes in topological order, and propagates confidence scores and provenance through the edges.

This document describes the structure of the SemanticGraph, the rules governing topological execution, lazy versus eager evaluation, invalidation on retraction, the full executor pipeline, cycle detection, and opportunities for parallel execution.

---

## The SemanticGraph

The SemanticGraph is a directed acyclic graph where:

- **FactNodes** are the vertices. Each FactNode holds a typed value, a confidence score, a provenance chain, and a tag set.
- **DependencyEdges** are directed edges from a derived FactNode to each FactNode that was used to derive it. An edge carries the rule or transform that established the dependency.

```
BaseFactNode ──rule: age-check──→ DerivedFactNode(can-vote)
     │                                      │
     └──────────────────────────────────────┘
         (confidence flows upward; retraction propagates downward)
```

Formally:

```
SemanticGraph = (V, E)
V = { FactNode(id, type, value, confidence, provenance, tags) }
E = { DependencyEdge(source: FactNode, target: FactNode, rule: RuleRef) }
```

The graph is acyclic at the fact level. Rules that would create a cycle (where a derived fact depends on itself, directly or transitively) are detected during load and raise a `CycleError`.

---

## FactNode Anatomy

```logos
FactNode {
    id         : NodeId          // globally unique identifier
    type       : LogosType       // the Logos type of the value
    value      : TypedValue      // the concrete value
    confidence : Float [0.0, 1.0]
    provenance : ProvenanceChain // ordered list of rule applications
    tags       : Set<Tag>
    state      : Pending | Computed | Retracted
}
```

A FactNode in state `Pending` has not yet been evaluated. `Computed` means its value and confidence are current. `Retracted` means the fact has been withdrawn; its dependents must be re-evaluated.

---

## Topological Execution Order

The executor processes FactNodes in topological order: for every DependencyEdge `(A → B)`, node `A` is processed before node `B`.

Topological sort is computed using Kahn's algorithm at load time:

1. Identify all nodes with in-degree zero (base facts — asserted directly, not derived).
2. Process each zero-in-degree node; emit it as ready.
3. Decrement the in-degree of each successor. If a successor reaches zero, add it to the ready queue.
4. Repeat until the queue is empty. If nodes remain unprocessed, a cycle exists.

Base facts are all nodes that have no incoming DependencyEdges. They are the roots of the graph.

```
Base facts (in-degree = 0):
    alice.age     → 30
    voting-age    → 18

Derived facts:
    can-vote(alice) ← rule: alice.age >= voting-age   [depends on both base facts]
```

The executor guarantees that `alice.age` and `voting-age` are in state `Computed` before it attempts to evaluate `can-vote(alice)`.

---

## Lazy vs. Eager Evaluation

The executor supports two evaluation strategies, selectable per context or per query:

### Eager Evaluation

All FactNodes reachable from the base facts are materialized immediately after assertion. This is appropriate for programs where most derived facts will be queried and where the graph is small enough to fit in memory.

```logos
context Production :
    evaluation : eager
```

Eager evaluation trades memory for query latency: queries are answered by lookup, not computation.

### Lazy Evaluation

FactNodes are materialized only when a query demands their value. The executor traces backward from the query target, identifies the minimal subgraph required, and evaluates only those nodes.

```logos
context Development :
    evaluation : lazy
```

Lazy evaluation is the default. It is appropriate for large graphs where only a small fraction of derived facts are queried in any given run.

### Demand-Driven Memoization

Regardless of strategy, once a FactNode is computed it is memoized. Subsequent queries for the same node return the cached value without re-evaluation. The cache is invalidated when any upstream node is retracted.

---

## How Derived Facts Depend on Base Facts

A derived fact D depends on a base fact B if there exists a directed path in the SemanticGraph from B to D. This is the **dependency closure** of D.

```
alice.age → can-vote(alice) → eligible-for-jury(alice)
                                          ↑
                 citizenship(alice) ──────┘
```

`eligible-for-jury(alice)` depends on both `can-vote(alice)` (which in turn depends on `alice.age`) and `citizenship(alice)`. The full dependency closure of `eligible-for-jury(alice)` is `{alice.age, voting-age, can-vote(alice), citizenship(alice)}`.

Confidence propagation follows the same edges: the confidence of a derived fact is a function (typically the product or minimum) of the confidences of its direct dependencies.

```
confidence(can-vote(alice))
    = min(confidence(alice.age), confidence(voting-age))
    * confidence(age-check rule)
```

---

## Invalidation on Retraction

When a fact is retracted, every FactNode that transitively depends on it must be invalidated:

1. The retracted node transitions to state `Retracted`.
2. The executor performs a forward BFS from the retracted node along DependencyEdges.
3. Every visited node transitions to state `Pending`.
4. The executor re-evaluates `Pending` nodes in topological order, considering whether their other dependencies still hold.
5. If a derived node's rule can no longer fire (because a required base fact is gone), the derived node is also retracted.

This process is **incremental re-evaluation**: only the affected subgraph is recomputed, not the entire graph.

```logos
retract alice.age          // alice.age → Retracted
// executor cascades: can-vote(alice) → Pending → re-evaluated → Retracted
// executor cascades: eligible-for-jury(alice) → Pending → re-evaluated → Retracted
```

---

## The Executor Pipeline

The executor processes a Logos program in five stages:

### Stage 1: Load

- Parse all source files.
- Resolve imports and merge module graphs.
- Build the initial SemanticGraph topology (nodes and edges) without evaluating values.
- Detect structural cycles (see Cycle Detection).

### Stage 2: Type-Check

- Verify that every FactNode's type matches the schema declared for that predicate.
- Verify that every DependencyEdge is type-compatible (the types flowing through a rule match the rule's input/output declarations).
- Verify that transform parameter types and return types are consistent with the calling context.
- Emit `TypeError` on any violation; halt before assertion.

### Stage 3: Assert

- Materialize base FactNodes from `assert` statements in source order.
- Assign confidence scores (explicit or default 1.0).
- Assign tags.
- Record provenance as `asserted-at: <source-location>`.

### Stage 4: Infer

- Execute inference rules in topological order over the graph.
- For eager contexts: materialize all derived nodes.
- For lazy contexts: defer until Stage 5 demands.
- Propagate confidence scores and provenance chains along DependencyEdges.
- On contradiction: apply the active context's `error-tolerance` policy.

### Stage 5: Query

- Accept query expressions from the program or external callers.
- For each query target, trigger lazy evaluation if needed.
- Apply the active context's confidence threshold and tag filters.
- Return result sets with provenance metadata.
- For streaming queries, yield results incrementally as nodes are computed.

The pipeline is re-entered at Stage 3 whenever new facts are asserted at runtime, and at Stage 4 whenever a retraction invalidates derived nodes.

---

## Cycle Detection

The SemanticGraph must be acyclic. The executor detects two kinds of cycles:

### Structural Cycle (Load-Time)

A structural cycle exists when a rule's conclusion appears in its own premise chain. This is detected during Stage 1 (Load) using a depth-first search on the dependency graph. Any back-edge indicates a structural cycle.

```logos
// ILLEGAL: structural cycle
rule self-referential :
    if can-vote(P) then can-vote(P)    // P's can-vote depends on itself
```

This raises a `CycleError` during load and prevents execution.

### Semantic Cycle via Transforms (Resolution-Time)

A transform that recursively invokes itself without a base case creates a resolution-time cycle. The executor maintains a **resolution stack** and raises a `CycleError` if the same transform with the same ground arguments appears twice on the stack.

Well-founded recursion is permitted:

```logos
transform reachable [start: Node, target: Node] → Boolean :
    intent : "BFS reachability in a graph"
    start = target                          // base case
    or exists mid :
        edge(start, mid)
        and reachable[start: mid, target: target]
```

The executor detects termination because the graph is finite and each recursive step strictly reduces the distance. Non-termination is detected by a configurable **recursion depth limit** (default: 1000 steps).

---

## Parallelism Opportunities

The topological ordering exposes natural parallelism: all nodes at the same **depth** in the DAG (i.e., with all their predecessors already computed) may be evaluated concurrently.

```
Depth 0 (base facts):       alice.age, voting-age, citizenship(alice)
Depth 1 (first inference):  can-vote(alice)           // depends on depth-0 only
Depth 2 (second inference): eligible-for-jury(alice)  // depends on depth-0 and depth-1
```

Nodes at depth 0 and depth 1 may be evaluated in parallel. Depth-2 nodes must wait for depth-1 to complete.

The executor uses a **work-stealing thread pool** where each worker thread takes a ready node from the queue, evaluates it, and then enqueues any successors whose in-degree has dropped to zero. This achieves maximum parallelism within the constraints of the DAG.

Thread safety: each FactNode has a single writer (the thread that evaluates it) and multiple readers (threads evaluating successors). The executor uses a read-write lock per node; writers acquire an exclusive lock during evaluation, then release it and signal readers.

### Parallelism Limits

- Transforms with side effects on external state are not parallelized (but transforms are pure in Logos, so this does not apply).
- Nodes that share a contradiction-detection scope are serialized to avoid race conditions in the error-tolerance logic.
- The parallelism degree is configurable: `executor.parallelism = N` (default: number of CPU cores).

---

## Example: Full Graph Walkthrough

```logos
assert Person : name = "Alice", age = 30, citizen = true
assert Person : name = "Bob",   age = 16, citizen = true
assert VotingAge : value = 18

rule can-vote :
    if Person.age >= VotingAge.value and Person.citizen = true
    then can-vote(Person) = true

rule eligible-for-jury :
    if can-vote(P) and P.age >= 21
    then eligible-for-jury(P) = true
```

Resulting SemanticGraph:

```
alice.age (30)     ──┐
alice.citizen(T)   ──┤── can-vote(alice) ──┬── eligible-for-jury(alice)
voting-age (18)    ──┘                     │
alice.age (30)     ───────────────────────-┘ (also dep of jury rule)

bob.age (16)       ──┐
bob.citizen(T)     ──┤── can-vote(bob) → NOT FIRED (age < 18)
voting-age (18)    ──┘
```

Topological execution order:
1. `alice.age`, `alice.citizen`, `bob.age`, `bob.citizen`, `voting-age` (parallel, depth 0)
2. `can-vote(alice)` — fires (30 >= 18, citizen = true)
3. `can-vote(bob)` — does not fire (16 < 18)
4. `eligible-for-jury(alice)` — fires (can-vote = true, age >= 21)
5. `eligible-for-jury(bob)` — does not fire (can-vote not derived)

---

## Summary

- The SemanticGraph is a DAG of FactNodes connected by DependencyEdges.
- Execution proceeds in topological order: base facts first, then derived facts by depth.
- Lazy evaluation defers node computation until demanded by a query; eager evaluation materializes all reachable nodes up front.
- Retraction triggers incremental re-evaluation of the affected subgraph only.
- The executor pipeline is: Load → Type-Check → Assert → Infer → Query.
- Cycle detection operates at load time (structural) and resolution time (recursive transforms).
- Parallelism is achieved by concurrent evaluation of nodes at the same DAG depth using a work-stealing thread pool.
