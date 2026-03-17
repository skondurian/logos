"""
SemanticGraph — the core runtime data structure for Logos.

The graph is a directed acyclic multigraph of FactNodes. Edges represent
derivation dependencies (derived-from relationships).

Key invariants:
  - Facts are never deleted; only retracted (retracted=True).
  - Contradictions are retained with full provenance.
  - Merge is commutative (both graphs retain their facts).
  - Topological order is always available (no cycles in derivation graph).
"""

from __future__ import annotations
import uuid
import warnings
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import networkx as nx

from logos.confidence import ConfidenceValue
from logos import errors as err


# ─── Provenance record ────────────────────────────────────────────────────────

@dataclass
class ProvenanceRecord:
    source: str               # "birth-record", "inferred", "user-assert", etc.
    rule_name: Optional[str] = None   # inference rule that derived this fact
    timestamp: Optional[str] = None   # wall-clock, set by executor if needed


# ─── Fact node ────────────────────────────────────────────────────────────────

@dataclass
class FactNode:
    """
    A single fact in the semantic graph.

    Identified by (subject, predicate) — but multiple FactNodes can share
    the same (subject, predicate) if they come from different provenances
    (e.g., contradictions).
    """
    id: str
    subject: str                          # e.g. "alice"
    predicate: str                        # e.g. "age"
    value: Any                            # the fact's value
    value_type: str                       # Logos type name e.g. "Duration"
    confidence: ConfidenceValue
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    derived_from: list[str] = field(default_factory=list)  # other fact IDs
    context_name: Optional[str] = None
    retracted: bool = False

    @staticmethod
    def make(subject: str, predicate: str, value: Any,
             value_type: str = "Entity",
             confidence: Optional[ConfidenceValue] = None,
             provenance_source: str = "user-assert",
             context_name: Optional[str] = None) -> "FactNode":
        conf = confidence if confidence is not None else ConfidenceValue.absolute()
        return FactNode(
            id=str(uuid.uuid4()),
            subject=subject,
            predicate=predicate,
            value=value,
            value_type=value_type,
            confidence=conf,
            provenance=[ProvenanceRecord(source=provenance_source)],
            context_name=context_name,
        )

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject, self.predicate)

    def __repr__(self) -> str:
        s = f"{self.subject}.{self.predicate} = {self.value!r}"
        s += f" {self.confidence!r}"
        if self.retracted:
            s += " [RETRACTED]"
        return s


# ─── Query result ─────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    found: bool
    facts: list[FactNode]
    confidence: ConfidenceValue

    @property
    def value(self) -> Any:
        if self.facts:
            return self.facts[0].value
        return None

    def __bool__(self) -> bool:
        return self.found and not self.confidence.is_impossible()


# ─── Semantic graph ───────────────────────────────────────────────────────────

class SemanticGraph:
    """
    Directed graph of FactNodes with derivation edges.

    Nodes: fact IDs
    Edges: fact_id → depends_on_fact_id
    """

    def __init__(self):
        self._graph: nx.DiGraph = nx.DiGraph()
        self._facts: dict[str, FactNode] = {}   # id → FactNode
        # Index: (subject, predicate) → list[fact_id]
        self._index: dict[tuple[str, str], list[str]] = {}

    # ── Assertion ─────────────────────────────────────────────────────────────

    def assert_fact(self, fact: FactNode) -> str:
        """
        Add a fact to the graph. Returns the fact ID.

        If a fact with the same (subject, predicate) already exists and has a
        different value, both are retained and a ContradictionWarning is issued.
        """
        existing = self._active_facts(fact.subject, fact.predicate)
        for ex in existing:
            if ex.value == fact.value and ex.context_name == fact.context_name:
                # Duplicate — merge provenance, keep highest confidence
                ex.provenance.extend(fact.provenance)
                if fact.confidence.point > ex.confidence.point:
                    ex.confidence = fact.confidence
                return ex.id
            else:
                warnings.warn(
                    f"Contradiction: {fact.subject}.{fact.predicate} "
                    f"was {ex.value!r}, now also {fact.value!r}. "
                    f"Both retained with provenance.",
                    err.ContradictionWarning,
                    stacklevel=4,
                )

        self._facts[fact.id] = fact
        self._graph.add_node(fact.id)
        for dep_id in fact.derived_from:
            if dep_id in self._graph:
                self._graph.add_edge(fact.id, dep_id)

        key = (fact.subject, fact.predicate)
        self._index.setdefault(key, []).append(fact.id)
        return fact.id

    def retract(self, subject: str, predicate: str,
                context_name: Optional[str] = None):
        """Mark matching active facts as retracted."""
        key = (subject, predicate)
        for fid in self._index.get(key, []):
            f = self._facts[fid]
            if not f.retracted:
                if context_name is None or f.context_name == context_name:
                    f.retracted = True

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(self, subject: str, predicate: str,
              context_name: Optional[str] = None,
              confidence_threshold: float = 0.0) -> QueryResult:
        """Return active facts matching (subject, predicate)."""
        facts = self._active_facts(subject, predicate, context_name)
        facts = [f for f in facts
                 if f.confidence.point >= confidence_threshold]
        if not facts:
            return QueryResult(found=False, facts=[], confidence=ConfidenceValue.impossible())
        # Return highest-confidence fact
        best = max(facts, key=lambda f: f.confidence.point)
        return QueryResult(found=True, facts=facts, confidence=best.confidence)

    def query_all_subjects(self, predicate: str,
                           context_name: Optional[str] = None) -> list[FactNode]:
        """Return all active facts with a given predicate (across subjects)."""
        results = []
        for key, fids in self._index.items():
            if key[1] != predicate:
                continue
            for fid in fids:
                f = self._facts[fid]
                if not f.retracted:
                    if context_name is None or f.context_name == context_name:
                        results.append(f)
        return results

    def all_active_facts(self,
                         context_name: Optional[str] = None) -> Iterator[FactNode]:
        for f in self._facts.values():
            if not f.retracted:
                if context_name is None or f.context_name == context_name:
                    yield f

    def _active_facts(self, subject: str, predicate: str,
                      context_name: Optional[str] = None) -> list[FactNode]:
        key = (subject, predicate)
        results = []
        for fid in self._index.get(key, []):
            f = self._facts[fid]
            if not f.retracted:
                if context_name is None or f.context_name == context_name:
                    results.append(f)
        return results

    # ── Graph operations ──────────────────────────────────────────────────────

    def topological_order(self) -> list[str]:
        """Return fact IDs in topological order (dependencies before dependents).
        Raises CycleDetectedError if the derivation graph has cycles."""
        try:
            return list(reversed(list(nx.topological_sort(self._graph))))
        except nx.NetworkXUnfeasible:
            cycle = nx.find_cycle(self._graph)
            raise err.CycleDetectedError([e[0] for e in cycle])

    def merge(self, other: "SemanticGraph") -> "SemanticGraph":
        """
        Return a new SemanticGraph containing facts from both graphs.
        Merge is commutative: order of self/other doesn't matter for the
        set of retained facts (both contribute their facts independently).
        """
        result = SemanticGraph()
        for f in self._facts.values():
            result.assert_fact(f)
        for f in other._facts.values():
            result.assert_fact(f)
        return result

    def fact_by_id(self, fid: str) -> Optional[FactNode]:
        return self._facts.get(fid)

    def __len__(self) -> int:
        return sum(1 for f in self._facts.values() if not f.retracted)

    def __repr__(self) -> str:
        return f"SemanticGraph({len(self)} active facts)"
