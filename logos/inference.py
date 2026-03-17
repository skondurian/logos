"""
Inference engine for Logos — SLD-resolution with backchaining.

The engine attempts to prove goals using inference rules and facts in the
semantic graph. Confidence propagates through rule chains with degradation.

Algorithm: backward chaining (top-down SLD resolution)
  - Start from a goal (predicate call or comparison)
  - Unify with rule heads to generate sub-goals
  - Recursively prove sub-goals
  - Collect bindings; propagate confidence (product × degradation)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from logos.ast_nodes import (
    InferenceRule, PredicateCall, Comparison, NegatedPredicate,
    Variable, Path, DurationLit, ArithExpr
)
from logos.confidence import ConfidenceValue, conjoin_all, DEFAULT_DEGRADATION
from logos.semantic_graph import SemanticGraph, FactNode, QueryResult
from logos import errors as err


MAX_DEPTH = 64


# ─── Substitution / bindings ──────────────────────────────────────────────────

Bindings = dict[str, Any]   # variable name → value


def unify_term(a: Any, b: Any, bindings: Bindings) -> Optional[Bindings]:
    """
    Attempt to unify term a with term b under current bindings.
    Returns extended bindings on success, None on failure.
    """
    a = walk(a, bindings)
    b = walk(b, bindings)

    if a == b:
        return bindings
    if isinstance(a, Variable):
        return {**bindings, a.name: b}
    if isinstance(b, Variable):
        return {**bindings, b.name: a}
    # Structural unification for lists/tuples
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return None
        for x, y in zip(a, b):
            bindings = unify_term(x, y, bindings)
            if bindings is None:
                return None
        return bindings
    return None


def walk(term: Any, bindings: Bindings) -> Any:
    """Recursively chase variable bindings."""
    while isinstance(term, Variable) and term.name in bindings:
        term = bindings[term.name]
    return term


def apply_bindings(term: Any, bindings: Bindings) -> Any:
    """Substitute all bound variables in term."""
    term = walk(term, bindings)
    if isinstance(term, Variable):
        return term  # unbound
    if isinstance(term, Path):
        new_parts = []
        for p in term.parts:
            if isinstance(p, Variable):
                new_parts.append(str(apply_bindings(p, bindings)))
            elif isinstance(p, str) and p and p[0].isupper():
                # Uppercase string path part — treat as variable name
                resolved = bindings.get(p, p)
                new_parts.append(str(resolved))
            else:
                new_parts.append(p)
        return Path(parts=new_parts)
    if isinstance(term, PredicateCall):
        return PredicateCall(
            name=term.name,
            args=[apply_bindings(a, bindings) for a in term.args]
        )
    return term


# ─── Proof result ─────────────────────────────────────────────────────────────

@dataclass
class Proof:
    success: bool
    bindings: Bindings = field(default_factory=dict)
    confidence: ConfidenceValue = field(default_factory=ConfidenceValue.absolute)
    explanation: list[str] = field(default_factory=list)

    @staticmethod
    def failure() -> "Proof":
        return Proof(success=False, confidence=ConfidenceValue.impossible())


# ─── Inference engine ────────────────────────────────────────────────────────

class InferenceEngine:

    def __init__(
        self,
        graph: SemanticGraph,
        rules: list[InferenceRule],
        max_depth: int = MAX_DEPTH,
        degradation: float = DEFAULT_DEGRADATION,
    ):
        self.graph = graph
        self.rules = rules
        self.max_depth = max_depth
        self.degradation = degradation

    # ── Public interface ──────────────────────────────────────────────────────

    def prove(self, goal: Any, bindings: Optional[Bindings] = None,
              depth: int = 0) -> Iterator[Proof]:
        """
        Yield all proofs of `goal` under `bindings`.
        May yield 0 proofs (failure) or multiple (non-determinism).
        """
        if depth > self.max_depth:
            raise err.DepthLimitError(self.max_depth)

        bindings = bindings or {}
        goal = apply_bindings(goal, bindings)

        if isinstance(goal, Comparison):
            yield from self._prove_comparison(goal, bindings, depth)
        elif isinstance(goal, NegatedPredicate):
            yield from self._prove_negation(goal, bindings, depth)
        elif isinstance(goal, PredicateCall):
            yield from self._prove_predicate(goal, bindings, depth)
        else:
            # Bare path — evaluate as a lookup
            yield from self._prove_path_lookup(goal, bindings, depth)

    def prove_first(self, goal: Any, bindings: Optional[Bindings] = None) -> Proof:
        """Return first proof, or Proof.failure()."""
        for proof in self.prove(goal, bindings):
            return proof
        return Proof.failure()

    def prove_all(self, goals: list[Any],
                  bindings: Optional[Bindings] = None,
                  depth: int = 0) -> Iterator[Proof]:
        """
        Prove a conjunction of goals, threading bindings and confidence.
        """
        yield from self._prove_conjunction(goals, bindings or {}, depth, [])

    # ── Internal ──────────────────────────────────────────────────────────────

    def _prove_conjunction(
        self, goals: list[Any], bindings: Bindings, depth: int,
        confidences: list[ConfidenceValue]
    ) -> Iterator[Proof]:
        if not goals:
            yield Proof(
                success=True,
                bindings=bindings,
                confidence=conjoin_all(confidences) if confidences
                           else ConfidenceValue.absolute(),
            )
            return
        head, *rest = goals
        for sub_proof in self.prove(head, bindings, depth):
            if sub_proof.success:
                yield from self._prove_conjunction(
                    rest,
                    {**bindings, **sub_proof.bindings},
                    depth,
                    confidences + [sub_proof.confidence],
                )

    def _prove_predicate(self, goal: PredicateCall, bindings: Bindings,
                         depth: int) -> Iterator[Proof]:
        # 1. Try matching against facts in the semantic graph
        yield from self._prove_from_facts(goal, bindings)
        # 2. Try matching against inference rules
        yield from self._prove_from_rules(goal, bindings, depth)

    def _prove_from_facts(self, goal: PredicateCall,
                          bindings: Bindings) -> Iterator[Proof]:
        """
        Interpret a predicate call as a graph lookup:
          predicate(subject) — look up subject.predicate
          predicate(subject, value) — verify subject.predicate = value
        """
        args = [apply_bindings(a, bindings) for a in goal.args]

        if len(args) == 1:
            subject_term = args[0]
            # A Path with a single part is treated as a subject
            if isinstance(subject_term, Path) and len(subject_term.parts) == 1:
                subject_term = subject_term.parts[0]
            if isinstance(subject_term, Variable):
                # find P where predicate(P) — iterate all subjects
                for fact in self.graph.query_all_subjects(goal.name):
                    new_b = unify_term(subject_term, fact.subject, bindings)
                    if new_b is not None:
                        yield Proof(
                            success=True,
                            bindings={**bindings, **new_b},
                            confidence=fact.confidence,
                            explanation=[f"fact:{fact.subject}.{goal.name}"],
                        )
            else:
                subject = _term_to_str(subject_term)
                result = self.graph.query(subject, goal.name)
                if result.found:
                    yield Proof(
                        success=True,
                        bindings=bindings,
                        confidence=result.confidence,
                        explanation=[f"fact:{subject}.{goal.name}"],
                    )

        elif len(args) == 2:
            subject_term, value_term = args
            if isinstance(subject_term, Variable):
                for fact in self.graph.query_all_subjects(goal.name):
                    new_b = unify_term(subject_term, fact.subject, bindings)
                    if new_b is not None:
                        new_b2 = unify_term(value_term, fact.value, new_b)
                        if new_b2 is not None:
                            yield Proof(
                                success=True,
                                bindings={**bindings, **new_b2},
                                confidence=fact.confidence,
                                explanation=[f"fact:{fact.subject}.{goal.name}"],
                            )
            else:
                subject = _term_to_str(subject_term)
                result = self.graph.query(subject, goal.name)
                if result.found:
                    new_b = unify_term(value_term, result.value, bindings)
                    if new_b is not None:
                        yield Proof(
                            success=True,
                            bindings={**bindings, **new_b},
                            confidence=result.confidence,
                            explanation=[f"fact:{subject}.{goal.name}"],
                        )

    def _prove_from_rules(self, goal: PredicateCall, bindings: Bindings,
                          depth: int) -> Iterator[Proof]:
        for rule in self.rules:
            if rule.head.name != goal.name:
                continue
            if len(rule.head.args) != len(goal.args):
                continue
            # Rename variables in rule to avoid capture
            rule = _rename_vars(rule, depth)
            # Unify goal args with rule head args
            new_b = dict(bindings)
            for goal_arg, rule_arg in zip(goal.args, rule.head.args):
                goal_arg = apply_bindings(goal_arg, new_b)
                new_b = unify_term(rule_arg, goal_arg, new_b)
                if new_b is None:
                    break
            else:
                # Prove all conditions
                for conj_proof in self._prove_conjunction(
                    rule.conditions, new_b, depth + 1, []
                ):
                    degraded = conj_proof.confidence.degrade(self.degradation)
                    yield Proof(
                        success=True,
                        bindings=conj_proof.bindings,
                        confidence=degraded,
                        explanation=[f"rule:{rule.head.name}"] + conj_proof.explanation,
                    )

    def _prove_comparison(self, goal: Comparison, bindings: Bindings,
                          depth: int) -> Iterator[Proof]:
        left = apply_bindings(goal.left, bindings)
        right = apply_bindings(goal.right, bindings)

        # If left is a path whose root is still unresolved (variable-like),
        # enumerate or resolve.
        if isinstance(left, Path) and len(left.parts) == 2:
            subject_raw, predicate = left.parts[0], left.parts[1]
            if isinstance(subject_raw, str) and not self.graph.query(subject_raw, predicate).found:
                right_val, right_conf = self._resolve_to_value(right, bindings)
                if right_val is None:
                    return
                # If subject_raw is already bound to a concrete subject, just look it up
                concrete_subject = bindings.get(subject_raw)
                if isinstance(concrete_subject, str):
                    result = self.graph.query(concrete_subject, str(predicate))
                    if result.found and _compare(result.value, goal.op, right_val):
                        conf = result.confidence.conjoin(right_conf)
                        yield Proof(success=True, bindings=bindings, confidence=conf)
                    return
                # subject_raw is unbound — enumerate all facts for this predicate
                for fact in self.graph.query_all_subjects(str(predicate)):
                    if _compare(fact.value, goal.op, right_val):
                        new_b = {**bindings, subject_raw: fact.subject}
                        conf = fact.confidence.conjoin(right_conf)
                        yield Proof(success=True, bindings=new_b, confidence=conf)
                return

        # Resolved path — standard comparison
        left_val, left_conf = self._resolve_to_value(left, bindings)
        right_val, right_conf = self._resolve_to_value(right, bindings)

        if left_val is None or right_val is None:
            return  # cannot evaluate

        result = _compare(left_val, goal.op, right_val)
        if result:
            conf = left_conf.conjoin(right_conf)
            yield Proof(success=True, bindings=bindings, confidence=conf)

    def _prove_negation(self, goal: NegatedPredicate, bindings: Bindings,
                        depth: int) -> Iterator[Proof]:
        """Negation-as-failure: succeed if the inner predicate has no proof."""
        proofs = list(self.prove(goal.predicate, bindings, depth))
        if not proofs:
            yield Proof(success=True, bindings=bindings,
                        confidence=ConfidenceValue.absolute())

    def _prove_path_lookup(self, path: Any, bindings: Bindings,
                           depth: int) -> Iterator[Proof]:
        if isinstance(path, Path) and len(path.parts) == 2:
            subject, predicate = path.parts
            result = self.graph.query(subject, predicate)
            if result.found:
                yield Proof(success=True, bindings=bindings,
                            confidence=result.confidence)
        elif isinstance(path, Path) and len(path.parts) == 1:
            yield Proof(success=True, bindings=bindings,
                        confidence=ConfidenceValue.absolute())

    def _resolve_to_value(self, term: Any,
                          bindings: Bindings) -> tuple[Any, ConfidenceValue]:
        term = apply_bindings(term, bindings)
        if isinstance(term, Path):
            if len(term.parts) == 2:
                subject, predicate = term.parts[0], term.parts[1]
                result = self.graph.query(str(subject), str(predicate))
                if result.found:
                    return result.value, result.confidence
            elif len(term.parts) == 1:
                # Single-part path — might be a value already looked up
                return term.parts[0], ConfidenceValue.absolute()
            return None, ConfidenceValue.impossible()
        if isinstance(term, Variable):
            # Try to resolve from bindings
            val = bindings.get(term.name)
            if val is not None:
                return val, ConfidenceValue.absolute()
            return None, ConfidenceValue.impossible()
        return term, ConfidenceValue.absolute()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _term_to_str(term: Any) -> str:
    if isinstance(term, Path):
        return str(term)
    return str(term)


def _compare(left: Any, op: str, right: Any) -> bool:
    """Evaluate a comparison, handling Duration and numeric types."""
    from logos.ast_nodes import DurationLit
    # Normalize durations to seconds
    if isinstance(left, DurationLit):
        left = left.to_seconds()
    if isinstance(right, DurationLit):
        right = right.to_seconds()
    try:
        if op == ">=": return left >= right
        if op == "<=": return left <= right
        if op == ">":  return left > right
        if op == "<":  return left < right
        if op == "=":  return left == right
        if op == "!=": return left != right
    except TypeError:
        return False
    return False


def _rename_vars(rule: InferenceRule, depth: int) -> InferenceRule:
    """Return a copy of rule with all variables renamed to avoid capture."""
    suffix = f"_d{depth}"

    def rename(term):
        if isinstance(term, Variable):
            return Variable(name=term.name + suffix)
        if isinstance(term, Path):
            new_parts = []
            for p in term.parts:
                if isinstance(p, Variable):
                    new_parts.append(rename(p))
                elif isinstance(p, str) and p and p[0].isupper():
                    # Uppercase string — treat as variable name, rename it
                    new_parts.append(p + suffix)
                else:
                    new_parts.append(p)
            return Path(parts=new_parts)
        if isinstance(term, PredicateCall):
            return PredicateCall(name=term.name,
                                 args=[rename(a) for a in term.args])
        if isinstance(term, Comparison):
            return Comparison(left=rename(term.left), op=term.op,
                              right=rename(term.right))
        if isinstance(term, NegatedPredicate):
            return NegatedPredicate(predicate=rename(term.predicate))
        return term

    new_head = PredicateCall(
        name=rule.head.name,
        args=[rename(a) for a in rule.head.args]
    )
    new_conditions = [rename(c) for c in rule.conditions]
    return InferenceRule(head=new_head, conditions=new_conditions)
