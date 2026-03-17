# Logos Language Specification — Chapter 5: Confidence Model

## 1. Overview

The confidence model is the mechanism by which Logos represents and propagates uncertainty through a knowledge base. Every fact in Logos has an associated confidence value, and every inference that derives new facts from existing facts propagates confidence according to well-defined arithmetic rules.

Confidence in Logos is grounded in **Bayesian probability**: a confidence value of 0.8 for a fact F means "we believe there is an 80% probability that F is true." This is a **degree of belief**, not a frequency or a logical truth value.

The model has three levels of sophistication:

1. **Absolute confidence** — certainty (the Dirac delta at 1.0). Used for facts known to be definitively true.
2. **Point estimate** — a single probability in [0, 1]. The common case for uncertain facts.
3. **Full distribution** — a probability distribution over [0, 1]. Used when we are uncertain about our uncertainty.

## 2. ConfidenceValue Structure

The `ConfidenceValue` type is the internal representation of a confidence annotation.

```logos
ConfidenceValue (Entity):
  estimate: Float           // point estimate in [0.0, 1.0]
  ci95-lower: Optional<Float>   // lower bound of 95% credible interval
  ci95-upper: Optional<Float>   // upper bound of 95% credible interval
  distribution: Optional<Text>  // distribution family name
  is-absolute: Boolean      // true iff this is a Dirac delta at 1.0
```

When `is-absolute` is `true`, the value represents **epistemic certainty** — not just high probability, but the absence of any probability mass anywhere except at 1.0. This is distinct from `estimate: 0.9999`: absolute confidence is a Dirac delta, not a point mass near 1.

### 2.1 Absolute Confidence

The keyword `absolute` is the canonical way to express certainty:

```logos
capital of France := "Paris" [confidence: absolute]
```

Absolute confidence has several special properties in arithmetic:
- `absolute ∧ X = X` (multiplying by absolute is identity)
- `absolute ∨ X = absolute` (absolute disjunction is always absolute)
- `absolute` propagates through inference rules without degradation

### 2.2 Point Estimate

A floating-point value in [0.0, 1.0]:

```logos
age of alice := 30 years [confidence: 0.95]
```

When only a point estimate is provided, the `ci95` bounds are absent and the distribution is treated as a degenerate (spike) distribution at that estimate.

### 2.3 Full Distribution (Beta)

The preferred distribution for modeling uncertainty about a probability is the **Beta distribution**, parameterized by shape parameters α (alpha) and β (beta). The Beta distribution is defined on [0, 1], making it the natural choice for modeling confidence values.

```logos
accuracy of sensor-1 := 0.92 [
  confidence: {
    estimate: 0.92
    ci95: [0.87, 0.96]
    distribution: "Beta"
    params: { alpha: 46.0, beta: 4.0 }
  }
]
```

**Beta distribution interpretation:**

The Beta(α, β) distribution can be interpreted as the posterior distribution for a probability after observing α − 1 successes and β − 1 failures out of α + β − 2 Bernoulli trials. This gives an intuitive meaning to the parameters:

| α | β | Interpretation |
|---|---|---------------|
| 100 | 1 | Very high confidence (99 successes, 0 failures) |
| 10 | 2 | High confidence (9 successes, 1 failure) |
| 5 | 5 | Uncertain (symmetric, centered at 0.5) |
| 1 | 1 | Uniform prior (complete ignorance) |
| 2 | 8 | Low confidence (1 success, 7 failures) |

**Converting between point estimate and Beta parameters:**

Given estimate `p` and sample size `n`:
- α = p × n
- β = (1 − p) × n

Given Beta(α, β):
- estimate = α / (α + β)
- variance = αβ / ((α+β)² × (α+β+1))

### 2.4 Named Confidence Shorthands

The following named shorthands are provided for convenience:

| Name | `estimate` | `ci95` | `distribution` |
|------|-----------|--------|----------------|
| `absolute` | 1.0 | [1.0, 1.0] | Dirac |
| `certain` | 0.99 | [0.97, 1.0] | Beta(99, 1) |
| `high` | 0.85 | [0.78, 0.91] | Beta(17, 3) |
| `medium` | 0.65 | [0.55, 0.74] | Beta(13, 7) |
| `low` | 0.40 | [0.30, 0.51] | Beta(8, 12) |
| `speculative` | 0.20 | [0.12, 0.30] | Beta(4, 16) |

## 3. Confidence Arithmetic

### 3.1 Conjunction (AND)

When two facts are combined with AND semantics (as in a rule body where all conditions must hold), confidences are **multiplied**:

```
confidence(A ∧ B) = confidence(A) × confidence(B)
```

This formula assumes **independence** of A and B. When A and B are not independent, this is an approximation. In practice, Logos uses this approximation for all conjunctions because tracking full joint distributions is computationally intractable.

**Example:**

```logos
// Fact 1: alice is American (confidence: 0.95)
// Fact 2: alice is over 18 (confidence: 0.90)
// Conjunction: alice is American AND over 18
// confidence = 0.95 × 0.90 = 0.855
```

**Point estimates:** Multiply the `estimate` fields.

**Beta distributions:** The product of two Beta distributions is not a Beta distribution, but for practical purposes Logos approximates it using moment matching:

```
estimate_result = estimate_A × estimate_B
variance_result ≈ variance_A × estimate_B² + variance_B × estimate_A²
```

Then fit a Beta(α, β) to the resulting estimate and variance.

### 3.2 Disjunction (OR)

When two facts are combined with OR semantics (alternative rules for the same conclusion), confidences are combined using the **probabilistic-or** formula:

```
confidence(A ∨ B) = 1 − (1 − confidence(A)) × (1 − confidence(B))
```

This is the inclusion-exclusion formula under the independence assumption.

**Example:**

```logos
// Rule 1 derives can-fly from being a bird (confidence: 0.80)
// Rule 2 derives can-fly from having wings (confidence: 0.70)
// Disjunction: can-fly via rule1 OR rule2
// confidence = 1 - (1 - 0.80) × (1 - 0.70)
//            = 1 - 0.20 × 0.30
//            = 1 - 0.06
//            = 0.94
```

### 3.3 Negation

Negation-as-failure has no direct confidence arithmetic: `not: condition` succeeds with confidence 1.0 if the condition has no proofs, and fails if the condition has any proof. For confidence-aware negation, the correct approach is to use the complement:

```
confidence(¬A) = 1 − confidence(A)
```

This is the **strong negation** form, syntactically distinct from negation-as-failure:

```logos
// Negation-as-failure (succeeds if condition cannot be proved)
not: citizen-of(alice, "France")

// Strong negation (confidence-arithmetic complement)
not-citizen-confidence := complement-of(confidence-of(citizen-of(alice, "France")))
```

### 3.4 Inference-Chain Degradation

Each step in an inference chain introduces a **degradation factor** to model the uncertainty introduced by applying the rule itself. The degradation factor is a value in (0, 1] that reflects our confidence that the rule's logical structure is correct.

```logos
can-vote(P) if:
  age of P >= 18 years
  nationality of P == "American"
  // Default degradation factor: 0.99 (rule is highly trusted)
```

To set a custom degradation factor for a rule:

```logos
can-vote(P) [degradation: 0.95] if:
  age of P >= 18 years
  nationality of P == "American"
```

**Confidence after applying a rule:**

```
confidence(conclusion) = degradation × ∏ confidence(premise_i)
```

For default rules (no explicit degradation), the degradation factor is **0.99**. This means that even for absolutely certain premises, a derived conclusion has confidence 0.99 rather than 1.0, reflecting the possibility that the rule itself is imperfect.

**Exception:** Rules with the `[trusted: true]` annotation use a degradation factor of 1.0. These are reserved for rules that are definitionally true (e.g., mathematical identities, definitional equivalences).

```logos
is-adult(P) [trusted: true] if:
  age of P >= 18 years
  // This is a definition; no degradation applied
```

### 3.5 Multi-Step Chain Degradation

In a chain of n inference steps, the total degradation is the product of per-step degradations:

```
confidence(final) = confidence(base-fact) × degradation_1 × degradation_2 × … × degradation_n
```

For default degradation (0.99) and n steps starting from an absolute fact:

| Steps | Cumulative Confidence |
|-------|----------------------|
| 1 | 0.99 |
| 5 | 0.951 |
| 10 | 0.904 |
| 20 | 0.818 |
| 50 | 0.605 |
| 100 | 0.366 |

This built-in degradation prevents very long inference chains from producing high-confidence conclusions without grounding in direct evidence — a desirable epistemic property.

## 4. The Fallback Chain Operator

The `|` operator provides a **fallback chain**: use the left operand if it produces a binding, otherwise fall through to the right operand.

```
FallbackExpr ::= Expr '|' Expr ('|' Expr)*
```

**Semantics:** Evaluate expressions left to right. Return the first expression that produces a binding with confidence above the current threshold. If no expression produces a binding, return no binding.

```logos
display-name of P := preferred-name of P | nickname of P | full-name of P | "Unknown"
```

**Confidence propagation in fallback chains:**

The confidence of the result is the confidence of the expression that was selected. There is no combination of confidences across the chain; it is a selection operation, not a conjunction.

**Example with confidence:**

```logos
// preferred-name of alice: no binding
// nickname of alice: "Ali" [confidence: 0.8]
// full-name of alice: "Alice Smith" [confidence: absolute]

display-name of alice := preferred-name of alice | nickname of alice | full-name of alice
// Result: "Ali" [confidence: 0.8]
// (The full-name binding is not reached because nickname succeeded)
```

## 5. Confidence Thresholds

Logos uses confidence thresholds to determine when a derived fact is "accepted" as a conclusion.

### 5.1 Default Threshold

The default acceptance threshold is **0.50**. Derived facts with confidence ≥ 0.50 are included in query results (by default). Facts below 0.50 are computed but not included in default query results.

### 5.2 Query-Level Threshold

A threshold can be specified per query:

```logos
find P where can-vote(P) [min-confidence: 0.80]
```

### 5.3 Context-Level Threshold

A context block can establish a threshold for all queries within it:

```logos
context high-confidence:
  threshold: 0.90

  find P where can-vote(P)
  // Only includes P where confidence >= 0.90
```

### 5.4 Zero-Threshold Mode

To retrieve all derived facts regardless of confidence:

```logos
find P where can-vote(P) [min-confidence: 0.0]
```

This is useful for debugging inference chains.

## 6. Confidence Combination for Multiple Bindings

When a query returns multiple bindings for the same `(subject, predicate)` pair (e.g., because of contradiction or multiple sources), the combined confidence depends on the interpretation:

### 6.1 Disjunctive Combination (Any of them is true)

If the bindings represent alternative values where any one being true would make the fact true:

```
confidence(at-least-one-is-true) = 1 − ∏(1 − confidence_i)
```

### 6.2 Conjunctive Combination (All of them agree)

If the bindings are independent attestations of the same fact (corroborating evidence):

```
confidence(all-agree) = min(confidence_i)   // conservative
// or
confidence(all-agree) ≈ 1 − (1 − product) × length  // anti-conservative approximation
```

Logos uses **conjunctive combination** for corroborating evidence by default, because multiple independent sources agreeing should increase confidence:

```
confidence(corroborated) = 1 − ∏(1 − confidence_i)
```

This treats each source as an independent "vote" for the fact. Three sources each with 0.7 confidence give:

```
1 − (1 − 0.7)³ = 1 − 0.027 = 0.973
```

### 6.3 Weighting by Source Trust

Sources may have declared trust levels. Confidence can be weighted by source trust before combination:

```logos
Source (Entity):
  name: Text
  trust-level: Float    // 0.0 to 1.0
```

Weighted confidence: `effective_confidence = raw_confidence × trust_level`.

## 7. How Confidence Flows Through Inference Rules

The complete algorithm for confidence propagation through a rule application:

```
function apply-rule(rule, bindings):
  // 1. Collect premise confidences
  premise_confidences = [confidence(b) for b in bindings.premises]

  // 2. Compute conjunction of premises
  conjunction_conf = ∏ premise_confidences

  // 3. Apply rule degradation
  degradation = rule.degradation ?? 0.99

  // 4. Final conclusion confidence
  conclusion_confidence = conjunction_conf × degradation

  // 5. If rule is trusted, skip degradation
  if rule.trusted:
    conclusion_confidence = conjunction_conf

  return conclusion_confidence
```

### 7.1 Complete Example

```logos
// Facts:
// age of alice := 30 years [confidence: 0.95]
// nationality of alice := "American" [confidence: 0.90]

// Rule:
// can-vote(P) [degradation: 0.98] if:
//   age of P >= 18 years
//   nationality of P == "American"

// Derivation:
// premise 1: age of alice >= 18 years
//   → evaluates age of alice = 30 years [0.95]
//   → 30 years >= 18 years is absolutely true
//   → confidence of this condition: 0.95 × absolute = 0.95

// premise 2: nationality of alice == "American"
//   → evaluates to 0.90

// conjunction: 0.95 × 0.90 = 0.855

// degradation: × 0.98

// final: 0.855 × 0.98 = 0.8379

// can-vote(alice) [confidence: 0.8379]
```

## 8. Confidence Comparison Semantics

When a rule condition involves a comparison (e.g., `age of P >= 18 years`), and the value being compared is uncertain, the comparison produces a confidence value that reflects the probability that the comparison is true.

For a numeric value with a distribution, this requires computing:

```
P(X >= threshold) = 1 − CDF(threshold)
```

where CDF is the cumulative distribution function of the value's distribution.

In practice, Logos uses a simplified model:

- If the value's point estimate satisfies the comparison, the comparison confidence is the value's confidence.
- If the value's point estimate does not satisfy the comparison, the comparison confidence is `1 − confidence` (reflecting that the fact might still satisfy the comparison, just with low probability).
- If the 95% CI straddles the threshold, a Beta-distribution-based probability is computed.

```logos
// age of bob := 17.5 years [confidence: 0.8, ci95: [16.0, 19.0]]
// Comparison: age of bob >= 18 years
// → 17.5 < 18, but CI includes values >= 18
// → P(age >= 18) ≈ P(Beta(...) >= 18) computed from the distribution
// → confidence of comparison ≈ 0.35
```

## 9. Displaying Confidence

The runtime formats confidence values for display as follows:

| Condition | Display |
|-----------|---------|
| `is-absolute = true` | `[confidence: absolute]` |
| No CI, estimate ≥ 0.99 | `[confidence: 0.99]` |
| No CI | `[confidence: 0.85]` |
| With CI | `[confidence: 0.85 (95% CI: 0.78–0.91)]` |
| Full distribution | `[confidence: 0.85 (95% CI: 0.78–0.91, Beta(17,3))]` |

In `find` query output, confidence is shown inline with each result unless `[show-confidence: false]` is specified.
