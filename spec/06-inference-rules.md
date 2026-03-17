# Logos Language Specification — Chapter 6: Inference Rules

## 1. Overview

Inference rules are the mechanism by which Logos derives new facts from existing ones. A rule states: "if these conditions hold, then this conclusion follows." The runtime evaluates rules on demand (lazy evaluation by default) or eagerly (for materialization), using **SLD-resolution backchaining** — the same algorithm underlying Prolog, but extended with confidence propagation, the open-world assumption, and depth and cycle limits.

Rules are first-class objects in the semantic graph. They can be queried, inspected, and (with care) modified.

## 2. Rule Syntax

### 2.1 Basic Rule Form

```
RuleDecl   ::= RuleHead RuleAnnotation? 'if' ':' NEWLINE BLOCK-START ConditionList BLOCK-END

RuleHead   ::= RuleName '(' VarList ')'
             | FieldName 'of' Var ':=' Expr   // field-derivation rule

RuleName   ::= kebab-case identifier
VarList    ::= Var (',' Var)*
Var        ::= UPPERCASE identifier | PascalCase identifier

RuleAnnotation ::= '[' RuleAnnotationKV+ ']'
RuleAnnotationKV ::= 'degradation' ':' Float
                   | 'trusted' ':' Boolean
                   | 'max-depth' ':' Integer
                   | 'priority' ':' Integer

ConditionList ::= Condition+

Condition  ::= SimpleCondition
             | NegationCondition
             | DisjunctionCondition
             | TypeCondition

SimpleCondition    ::= Expr CompOp Expr NEWLINE
                     | RuleName '(' ArgList ')' NEWLINE
                     | FieldName 'of' Var NEWLINE  // binds Var to all entities with that field

NegationCondition  ::= 'not' ':' Condition

DisjunctionCondition ::= 'or' ':' NEWLINE BLOCK-START ConditionList BLOCK-END

TypeCondition      ::= Var '::' TypeName NEWLINE

CompOp  ::= '==' | '!=' | '<' | '<=' | '>' | '>='
```

### 2.2 Simplest Rule

```logos
adult(P) if:
  age of P >= 18 years
```

This rule defines a predicate `adult` that is true for any entity P whose age is at least 18 years. The rule has a single condition. `P` is a free variable that will be unified with entities from the knowledge base during proof search.

### 2.3 Multi-Condition Rule (AND Semantics)

Multiple conditions in a rule body are implicitly joined with AND. All conditions must hold for the rule to succeed.

```logos
can-vote(P) if:
  P :: Person
  age of P >= 18 years
  nationality of P == "American"
```

All three conditions must be satisfied simultaneously. The confidence of the conclusion is the product of the premise confidences times the degradation factor.

### 2.4 Rule with Field Derivation

A rule can derive the value of a field rather than a Boolean predicate:

```logos
full-name of P := concat(first-name of P, " ", last-name of P) if:
  first-name of P
  last-name of P
```

This derives the `full-name` field of P from its `first-name` and `last-name` fields whenever both are present.

### 2.5 Rule Annotations

```logos
can-retire(P) [degradation: 0.95, priority: 10] if:
  P :: Employee
  age of P >= 65 years
```

| Annotation | Type | Default | Meaning |
|------------|------|---------|---------|
| `degradation` | Float (0,1] | 0.99 | Per-application confidence reduction |
| `trusted` | Boolean | false | If true, degradation is 1.0 |
| `max-depth` | Integer | 100 | Maximum recursion depth for this rule |
| `priority` | Integer | 0 | Rule selection priority (higher = tried first) |

## 3. SLD-Resolution Backchaining

### 3.1 The Algorithm

SLD-resolution (Selective Linear Definite-clause resolution) is a form of top-down, depth-first search for proofs. Given a query `can-vote(alice)`, the algorithm:

1. **Goal selection:** Select the leftmost unsolved goal: `can-vote(alice)`.
2. **Rule matching:** Find all rules whose head unifies with `can-vote(alice)`. In this case: the `can-vote(P)` rule, with unification `P = alice`.
3. **Subgoal expansion:** Replace the goal with the rule's body conditions: `alice :: Person`, `age of alice >= 18 years`, `nationality of alice == "American"`.
4. **Recursive proof:** Prove each subgoal in order. For `age of alice >= 18 years`, look up `age of alice` in the knowledge base.
5. **Success:** If all subgoals succeed, the original goal succeeds. Collect the variable bindings and confidence.
6. **Backtracking:** If any subgoal fails, backtrack to the most recent choice point (another applicable rule) and try the next alternative.

### 3.2 Backtracking and Multiple Solutions

When a goal can be proved in multiple ways (multiple applicable rules, or multiple matching facts), the runtime explores all paths by default. Each path produces a separate result with its own confidence.

```logos
// Two ways to prove "can-travel(P, Country)":
can-travel(P, Country) if:
  passport-holder(P, Country)

can-travel(P, Country) if:
  visa-holder(P, Country)

// If alice has a passport for France AND a visa for France,
// can-travel(alice, France) is proved twice.
// The runtime combines the two confidences using disjunction:
// confidence = 1 - (1 - conf_passport) × (1 - conf_visa)
```

### 3.3 Lazy Evaluation

By default, Logos uses **lazy evaluation**: rules are only applied when a query needs a derived fact. The semantic graph stores only base facts; derived facts are computed on demand and optionally cached.

This is in contrast to **eager evaluation** (forward chaining), where all applicable rules are applied at load time. Eager evaluation is available as a directive:

```logos
// Force eager evaluation of this rule
can-vote(P) [eager: true] if:
  ...
```

## 4. Unification

Unification is the process of matching a query or rule head against facts and other rule heads. Two terms **unify** if there is a substitution for their variables that makes them syntactically identical.

### 4.1 Unification Rules

| Left | Right | Result |
|------|-------|--------|
| `alice` (constant) | `alice` (constant) | Succeed, no substitution |
| `alice` | `bob` | Fail |
| `P` (unbound variable) | `alice` (constant) | Succeed, `P = alice` |
| `P` (bound to `alice`) | `alice` | Succeed |
| `P` (bound to `alice`) | `bob` | Fail |
| `P` (unbound) | `Q` (unbound) | Succeed, `P = Q` (shared variable) |

### 4.2 Variable Convention

By convention, **uppercase** identifiers are free variables in rules:

```logos
can-vote(P) if:        // P is a free variable
  age of P >= 18 years // same P — must unify to the same entity
```

Lowercase identifiers are entity references (constants):

```logos
is-alice-adult if:
  age of alice >= 18 years  // alice is a constant, not a variable
```

The parser distinguishes variables from constants by their casing, not by declaration. This is a convention enforced by the linter but not the parser itself.

### 4.3 Structural Unification

Logos supports structural unification for record values:

```logos
has-complete-address(P) if:
  address of P == { street: _, city: _, state: _, zip: _ }
  // _ is the anonymous variable — matches anything, not bound
```

The anonymous variable `_` matches any value without binding. Each occurrence of `_` is a fresh variable.

## 5. Variables: Scope and Binding

### 5.1 Rule-Scoped Variables

Variables introduced in a rule are scoped to that rule. The same variable name in two different rules is two different variables.

### 5.2 Shared Variables

Within a single rule, the same variable name refers to the same entity across all conditions:

```logos
same-employer(P, Q) if:
  employer of P == E    // E bound to P's employer
  employer of Q == E    // Q must have the SAME employer E
  P != Q                // P and Q are different people
```

### 5.3 Singleton Variable Warning

A variable that appears only once in a rule is a **singleton** and is likely a mistake (it provides no constraint). The linter warns:

```logos
can-vote(P) if:
  age of Q >= 18 years   // WARNING: Q is a singleton; did you mean P?
```

Use `_` for intentional anonymous variables:

```logos
has-any-age(P) if:
  age of P == _   // valid: _ is explicitly anonymous
```

## 6. Multiple Rule Heads (Disjunctive Rules)

A predicate can be defined by multiple rules. Each rule provides an independent way to prove the predicate. This is **disjunctive** reasoning: the predicate holds if any one rule succeeds.

```logos
// A person can fly if they are a licensed pilot
can-fly(P) if:
  P :: Person
  has-license(P, "pilot")

// A person can fly if they have a valid flight booking
can-fly(P) if:
  P :: Person
  has-booking(P, Flight)
  Flight :: CommercialFlight
  departure-time of Flight > now
```

Both rules contribute to `can-fly`. If alice has a pilot license with confidence 0.9, and also has a flight booking with confidence 0.8, then `can-fly(alice)` has confidence:

```
confidence = 1 - (1 - 0.9 × degradation) × (1 - 0.8 × degradation)
           = 1 - (1 - 0.891) × (1 - 0.792)
           = 1 - 0.109 × 0.208
           = 1 - 0.0227
           = 0.977
```

(using degradation = 0.99)

## 7. Negation-as-Failure

Negation-as-failure (NAF) is the inference that a condition is false because no proof of its truth can be found. It is the standard form of negation in Logos (and in Prolog).

```logos
is-not-citizen(P, Country) if:
  not: citizen-of(P, Country)
```

### 7.1 Semantics

`not: condition` succeeds (with confidence 1.0) if and only if `condition` has **no proofs** in the current knowledge base. It fails if `condition` has at least one proof.

NAF interacts with the open-world assumption: under OWA, the absence of a proof does not mean the condition is definitively false — it means we have no evidence for it. NAF is therefore a **epistemic** operator: it succeeds when we have no knowledge of the condition, not when we know it is false.

### 7.2 NAF and Confidence

NAF does not propagate confidence in the same way as positive conditions. The result of a successful NAF has confidence equal to the rule's degradation factor (since we are relying on the absence of evidence, which is itself a weak form of evidence).

```logos
unregistered-voter(P) [degradation: 0.80] if:
  P :: Person
  age of P >= 18 years
  nationality of P == "American"
  not: registered-voter(P)
  // The not: condition carries the degradation cost
```

### 7.3 Safe Negation

A rule condition using `not:` is **safe** if all variables appearing in the negated condition also appear in positive conditions earlier in the rule body. Unsafe negation is a static error:

```logos
// SAFE: P appears in positive conditions before not:
is-not-citizen(P, "France") if:
  P :: Person               // P bound here
  not: citizen-of(P, "France")  // P is safe

// UNSAFE: Q appears only in the negated condition
bad-rule(P) if:
  P :: Person
  not: knows(P, Q)    // ERROR: Q is not bound by any positive condition
```

### 7.4 Stratified Negation

Logos requires **stratified negation**: no rule may (directly or indirectly) use NAF on a predicate that is derived by rules that depend on the same NAF. Non-stratified negation leads to paradoxes and is a static error.

```logos
// STRATIFIED (fine): p depends on not-q; q does not depend on p
p(X) if: not: q(X)
q(X) if: r(X)

// NON-STRATIFIED (error): p and q mutually depend via negation
p(X) if: not: q(X)
q(X) if: not: p(X)   // ERROR: mutual NAF dependency
```

## 8. Depth Limit

To prevent infinite recursion, Logos enforces a **maximum inference depth** — the maximum number of rule applications along any single proof branch.

### 8.1 Default Depth Limit

The default maximum depth is **100**. This is sufficient for the vast majority of practical knowledge bases.

### 8.2 Configuring Depth Limits

```logos
// Global configuration
config:
  max-inference-depth: 200

// Per-rule override
ancestor-of(X, Y) [max-depth: 50] if:
  parent-of(X, Y)

ancestor-of(X, Y) [max-depth: 50] if:
  parent-of(X, Z)
  ancestor-of(Z, Y)   // recursive; depth limit applied here
```

### 8.3 Depth Limit Exceeded

When the depth limit is reached, the current proof branch **fails** (not an error; simply no proof found along that path). The runtime logs a warning. If all branches fail due to depth limits, the query returns no result with a note indicating the depth limit was reached.

## 9. Cycle Detection

Beyond depth limits, Logos performs **cycle detection** to prevent infinite loops in mutually recursive rules.

### 9.1 Visited-Goals Table

The runtime maintains a **visited-goals table** per proof branch: a set of `(rule, substitution)` pairs that have been entered on the current proof path. If the same pair is encountered again, the branch is marked as cyclic and fails.

```logos
// Cyclic rule: is-connected(A, B) can loop
is-connected(A, B) if:
  edge(A, B)

is-connected(A, B) if:
  edge(A, C)
  is-connected(C, B)   // may revisit is-connected(A, B) via a cycle
```

In the cyclic case, the runtime detects the revisit and fails that branch, allowing other branches to continue. This ensures termination.

### 9.2 Tabling (Memoization)

For recursive rules, Logos optionally uses **tabling** (memoization of sub-goals) to avoid redundant recomputation and to handle some forms of mutual recursion:

```logos
is-ancestor(X, Y) [tabled: true] if:
  parent-of(X, Y)

is-ancestor(X, Y) [tabled: true] if:
  parent-of(X, Z)
  is-ancestor(Z, Y)
```

With `tabled: true`, each `(rule, substitution)` pair is computed at most once and the result is cached for the duration of the query.

## 10. Confidence Propagation Through Rule Chains

### 10.1 Single Rule

As defined in Chapter 5, applying a single rule:

```
confidence(conclusion) = degradation × ∏ confidence(premise_i)
```

### 10.2 Chained Rules

For a chain of n rules, each with degradation d_i and premises with confidence c_{i,j}:

```
confidence(final) = ∏_i [ d_i × ∏_j c_{i,j} ]
```

### 10.3 Worked Example: Three-Level Chain

```logos
// Level 1: base facts
age of alice := 30 years [confidence: 0.95]
nationality of alice := "American" [confidence: 0.99]
employed-at of alice := acme-corp [confidence: 0.90]

// Level 2: derived predicate
employed-adult(P) [degradation: 0.98] if:
  adult(P)               // derived from level 3
  employed-at of P       // base fact

// Level 3: intermediate
adult(P) [degradation: 0.99] if:
  age of P >= 18 years

// Query: employed-adult(alice)
//
// Step 1: prove adult(alice)
//   age of alice = 30 years [0.95]
//   30 >= 18: absolute
//   adult(alice) confidence = 0.99 × 0.95 = 0.9405
//
// Step 2: prove employed-adult(alice)
//   adult(alice) [0.9405]
//   employed-at of alice [0.90]
//   conjunction: 0.9405 × 0.90 = 0.8465
//   degradation: × 0.98
//   employed-adult(alice) confidence = 0.8295
```

## 11. The `find` Query Form

The `find` expression is the primary way to query the knowledge base and trigger inference.

### 11.1 Syntax

```
FindExpr ::= 'find' FindTarget ('where' ConditionList)? FindOptions?

FindTarget ::= VarList
             | FieldName 'of' Var
             | RuleName '(' VarList ')'

FindOptions ::= '[' FindOption+ ']'
FindOption  ::= 'min-confidence' ':' Float
              | 'max-results' ':' Integer
              | 'order-by' ':' ('confidence' | 'recency' | FieldName) ('desc')?
              | 'include-retracted' ':' Boolean
              | 'show-confidence' ':' Boolean
              | 'explain' ':' Boolean
```

### 11.2 Basic Find

```logos
// Find all people who can vote
find P where can-vote(P)

// Find alice's age
find age of alice

// Find all employees and their employers
find P, E where
  P :: Employee
  employer of P == E
```

### 11.3 Find with Conditions

```logos
find P where
  P :: Person
  age of P >= 18 years
  age of P < 65 years
  nationality of P == "American"
```

### 11.4 Find with Options

```logos
// Find all voters, showing only high-confidence results, ordered by confidence
find P where can-vote(P) [
  min-confidence: 0.80
  order-by: confidence desc
  max-results: 10
]
```

### 11.5 Find with Explanation

```logos
find P where can-vote(P) [explain: true]
```

Output includes a proof tree for each result:

```
alice [confidence: 0.8379]
  ← can-vote rule applied [degradation: 0.98]
    ← age of alice >= 18 years
        ← age of alice = 30 years [source: "passport", confidence: 0.95]
    ← nationality of alice == "American"
        ← nationality of alice = "American" [source: "census", confidence: 0.90]
```

### 11.6 Aggregation in Find

```logos
// Count how many people can vote
find count(P) where can-vote(P)

// Average age of voters
find avg(age of P) where can-vote(P)

// Maximum salary among executives
find max(salary of E) where E :: Executive
```

Supported aggregation functions: `count`, `sum`, `avg`, `min`, `max`, `list`, `set`.

## 12. Recursive Rules

Recursive rules are supported with the depth-limit and cycle-detection safeguards described in Sections 8 and 9.

### 12.1 Transitive Closure

```logos
// is-ancestor: transitive closure of parent-of
is-ancestor(X, Y) if:
  parent-of(X, Y)

is-ancestor(X, Y) if:
  parent-of(X, Z)
  is-ancestor(Z, Y)
```

### 12.2 Recursive Aggregation

```logos
// Total number of reports under an executive (recursive)
report-count of E := 1 + sum(report-count of R) if:
  E :: Executive
  reports-to of R == E
```

### 12.3 Mutual Recursion

Two or more rules may refer to each other, subject to the stratified negation constraint:

```logos
is-reachable(A, B) if:
  directly-connected(A, B)

is-reachable(A, B) if:
  directly-connected(A, C)
  is-reachable(C, B)
```

## 13. Built-in Predicates

Logos provides a set of built-in predicates available without declaration:

| Predicate | Description |
|-----------|-------------|
| `X :: T` | X is ascribed type T (or a subtype of T) |
| `X == Y` | X and Y are equal |
| `X != Y` | X and Y are not equal |
| `X < Y` | X is less than Y |
| `X > Y` | X is greater than Y |
| `X <= Y` | X is less than or equal to Y |
| `X >= Y` | X is greater than or equal to Y |
| `bound(X)` | True if X has a binding in the current scope |
| `unbound(X)` | True if X has no binding |
| `confidence-of(X) >= C` | True if the binding of X has confidence ≥ C |
| `type-of(X) == T` | True if the most specific type of X is exactly T |
| `subtype-of(S, T)` | True if type S IS-A T (in the type lattice) |
| `member(X, List)` | True if X appears in List |
| `length(List) == N` | True if List has N elements |
| `now` | The current DateTime |
| `today` | The current Date |

## 14. Complete Example: Eligibility Reasoning

The following example brings together rules, confidence propagation, negation, and queries in a realistic scenario.

```logos
// Types
type Person IS-A Entity
  fields:
    name: HumanName
    date-of-birth: Date?
    nationality: Text?

type RegisteredVoter IS-A Person
  fields:
    registration-date: Date
    registration-state: Text

type Felon IS-A Person
  fields:
    conviction-date: Date
    sentence-completed: Boolean

// Base facts
name of alice       := { first: "Alice", last: "Smith" }
date-of-birth of alice := @1994-03-15
nationality of alice := "American"
alice :: RegisteredVoter
registration-date of alice := @2012-09-01
registration-state of alice := "IL"

name of bob       := { first: "Bob", last: "Jones" }
date-of-birth of bob := @2009-11-20 [confidence: 0.85]
nationality of bob := "American"

name of carlos    := { first: "Carlos", last: "Reyes" }
date-of-birth of carlos := @1978-05-10
nationality of carlos := "Mexican"

// Inference rules
age-as-of-today(P, Age) [trusted: true] if:
  date-of-birth of P == DOB
  Age := duration-between(DOB, today)

is-adult(P) if:
  age-as-of-today(P, Age)
  Age >= 18 years

is-citizen(P, Country) if:
  nationality of P == Country

voting-eligible(P) if:
  is-adult(P)
  is-citizen(P, "American")
  not: P :: Felon

registered-and-eligible(P) if:
  P :: RegisteredVoter
  voting-eligible(P)

// Queries
find P where voting-eligible(P) [
  min-confidence: 0.75
  order-by: confidence desc
  explain: true
]
```

**Expected output:**

```
Results for: find P where voting-eligible(P) [min-confidence: 0.75]

alice [confidence: 0.970]
  ← voting-eligible [degradation: 0.99]
    ← is-adult(alice) [confidence: 0.990]
        ← age-as-of-today: 31 years 11 months [trusted, confidence: absolute]
        ← 31 years >= 18 years [absolute]
    ← is-citizen(alice, "American") [confidence: 0.990]
        ← nationality of alice = "American" [absolute]
    ← not: alice :: Felon → succeeded (no Felon ascription found) [absolute]

1 result(s). bob excluded: age confidence 0.85 → voting-eligible confidence 0.73 < threshold 0.75.
carlos excluded: nationality is "Mexican", not "American".
```
