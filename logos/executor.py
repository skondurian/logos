"""
Executor — orchestrates the load → type-check → assert → infer → query pipeline.

The Executor is the main entry point for running Logos programs. It holds:
  - A TypeLattice (type system)
  - A SemanticGraph (fact store)
  - A ContextRegistry
  - A list of InferenceRules
  - An InferenceEngine (lazy-constructed)
"""

from __future__ import annotations
import os
import warnings

# Stdlib directory ships alongside the logos package
_STDLIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stdlib")
from dataclasses import dataclass, field
from typing import Any, Optional

from logos.ast_nodes import (
    Program, Statement, TypeDecl, SemanticBinding, Retraction,
    InferenceRule, TransformDecl, ContextDecl, BoolQuery, FindQuery,
    ImportStmt, Path, DurationLit, Annotations, Variable, PredicateCall,
    Comparison,
)
from logos.confidence import ConfidenceValue, from_annotation, disjoin_all
from logos.context import Context, ContextRegistry
from logos.inference import InferenceEngine, Proof
from logos.semantic_graph import SemanticGraph, FactNode, QueryResult
from logos.type_system import TypeLattice
from logos import errors as err


@dataclass
class QueryOutput:
    """Result of executing a BoolQuery or FindQuery."""
    query_text: str
    results: list[dict]  # list of binding dicts with confidence
    confidence: ConfidenceValue

    @property
    def is_true(self) -> bool:
        # A query is TRUE if any proof was found; confidence is informational only.
        # Deep inference chains (e.g. compiler.logos) can degrade confidence to
        # near-zero while still finding a valid proof.
        return bool(self.results)

    def __repr__(self) -> str:
        if self.is_true:
            return f"{self.query_text} → TRUE  [{self.confidence!r}]"
        return f"{self.query_text} → FALSE"


class Executor:

    def __init__(self, search_path: Optional[list[str]] = None):
        self.type_lattice = TypeLattice()
        self.graph = SemanticGraph()
        self.context_registry = ContextRegistry()
        self.rules: list[InferenceRule] = []
        self.transforms: dict[str, TransformDecl] = {}
        # Always include the stdlib directory so `import stdlib/lists` works
        base_path = search_path if search_path is not None else ["."]
        self.search_path: list[str] = base_path + [
            os.path.dirname(os.path.abspath(__file__))
        ]
        self._engine: Optional[InferenceEngine] = None
        self._loaded_files: set[str] = set()

    @property
    def engine(self) -> InferenceEngine:
        """Lazy-construct inference engine (invalidated when rules/context change)."""
        if self._engine is None:
            active = self.context_registry.active_context_names()
            # Use the most recently activated non-default context, if any
            ctx_name = next(
                (n for n in reversed(active)
                 if n != ContextRegistry.DEFAULT_NAME),
                None
            )
            threshold = self.context_registry.effective_threshold(ctx_name)
            self._engine = InferenceEngine(
                self.graph, self.rules,
                confidence_threshold=threshold,
                active_context=ctx_name,
            )
        return self._engine

    def _invalidate_engine(self):
        self._engine = None

    # ── Loading ───────────────────────────────────────────────────────────────

    def load(self, program: Program) -> list[QueryOutput]:
        """Execute all statements in a Program, return query outputs."""
        outputs = []
        for stmt in program.statements:
            out = self.execute_statement(stmt)
            if out is not None:
                outputs.append(out)
        return outputs

    def load_file(self, path: str) -> list[QueryOutput]:
        """Parse and execute a .logos file."""
        from logos.parser import parse_file
        if path in self._loaded_files:
            return []
        self._loaded_files.add(path)
        program = parse_file(path)
        return self.load(program)

    def load_source(self, source: str) -> list[QueryOutput]:
        """Parse and execute a source string."""
        from logos.parser import parse
        program = parse(source)
        return self.load(program)

    # ── Statement dispatch ────────────────────────────────────────────────────

    def execute_statement(self, stmt: Statement) -> Optional[QueryOutput]:
        if isinstance(stmt, TypeDecl):
            self._exec_type_decl(stmt)
        elif isinstance(stmt, SemanticBinding):
            self._exec_binding(stmt)
        elif isinstance(stmt, Retraction):
            self._exec_retraction(stmt)
        elif isinstance(stmt, InferenceRule):
            self._exec_rule(stmt)
        elif isinstance(stmt, TransformDecl):
            self._exec_transform(stmt)
        elif isinstance(stmt, ContextDecl):
            self._exec_context(stmt)
        elif isinstance(stmt, BoolQuery):
            return self._exec_bool_query(stmt)
        elif isinstance(stmt, FindQuery):
            return self._exec_find_query(stmt)
        elif isinstance(stmt, ImportStmt):
            self._exec_import(stmt)
        return None

    # ── Type declarations ─────────────────────────────────────────────────────

    def _exec_type_decl(self, decl: TypeDecl):
        self.type_lattice.register(decl)

    # ── Semantic bindings ─────────────────────────────────────────────────────

    def _exec_binding(self, binding: SemanticBinding):
        subject, predicate = self._decompose_path(binding.path)
        value = self._eval_value(binding.value)
        value_type = self._infer_value_type(value)
        confidence = self._resolve_confidence(binding.annotations)
        provenance_source = (binding.annotations.provenance.source
                             if binding.annotations.provenance
                             else "user-assert")
        context_name = binding.annotations.context_name

        fact = FactNode.make(
            subject=subject,
            predicate=predicate,
            value=value,
            value_type=value_type,
            confidence=confidence,
            provenance_source=provenance_source,
            context_name=context_name,
        )
        self.graph.assert_fact(fact)
        self._invalidate_engine()

    def _decompose_path(self, path: Path) -> tuple[str, str]:
        """Convert a path to (subject, predicate)."""
        if len(path.parts) == 1:
            return path.parts[0], "value"
        return path.parts[0], ".".join(path.parts[1:])

    def _eval_value(self, value: Any) -> Any:
        """Evaluate a value node to a Python native value."""
        from logos.ast_nodes import ArithExpr, SetLit, ListLit
        if isinstance(value, ArithExpr):
            left = self._eval_value(value.left)
            right = self._eval_value(value.right)
            return _apply_op(left, value.op, right)
        if isinstance(value, SetLit):
            return frozenset(self._eval_value(e) for e in value.elements)
        if isinstance(value, ListLit):
            return [self._eval_value(e) for e in value.elements]
        if isinstance(value, Path):
            # Inline path reference — look up in graph
            if len(value.parts) == 2:
                result = self.graph.query(value.parts[0], value.parts[1])
                if result.found:
                    return result.value
            return value  # keep as-is (unresolved reference)
        return value  # DurationLit, str, int, float, bool, None

    def _infer_value_type(self, value: Any) -> str:
        if isinstance(value, DurationLit):
            return "Duration"
        if isinstance(value, bool):
            return "Boolean"
        if isinstance(value, int):
            return "Integer"
        if isinstance(value, float):
            return "Float"
        if isinstance(value, str):
            return "Text"
        if isinstance(value, frozenset):
            return "Set"
        if isinstance(value, list):
            return "List"
        return "Entity"

    def _resolve_confidence(self, annotations: Annotations) -> ConfidenceValue:
        if annotations.confidence:
            return from_annotation(annotations.confidence.raw)
        return ConfidenceValue.absolute()

    # ── Retraction ────────────────────────────────────────────────────────────

    def _exec_retraction(self, ret: Retraction):
        subject, predicate = self._decompose_path(ret.path)
        self.graph.retract(subject, predicate)
        self._invalidate_engine()

    # ── Inference rules ────────────────────────────────────────────────────────

    def _exec_rule(self, rule: InferenceRule):
        self.rules.append(rule)
        self._invalidate_engine()

    # ── Transforms ────────────────────────────────────────────────────────────

    def _exec_transform(self, decl: TransformDecl):
        self.transforms[decl.name] = decl

    # ── Contexts ──────────────────────────────────────────────────────────────

    def _exec_context(self, decl: ContextDecl):
        ctx = Context.from_decl(decl)
        self.context_registry.register(ctx)
        self._invalidate_engine()  # threshold may have changed

    def activate_context(self, name: str):
        """Activate a named context, applying its confidence threshold."""
        self.context_registry.activate(name)
        self._invalidate_engine()

    # ── Queries ───────────────────────────────────────────────────────────────

    def _exec_bool_query(self, query: BoolQuery) -> QueryOutput:
        query_text = f"{query.predicate.name}({', '.join(str(a) for a in query.predicate.args)})"

        # Collect all proofs and OR-combine their confidences.
        # P(A derived by any of N independent rules) = 1 - ∏(1 - pᵢ)
        all_confidences = [
            p.confidence for p in self.engine.prove(query.predicate)
            if p.success
        ]
        if not all_confidences:
            return QueryOutput(
                query_text=query_text,
                results=[],
                confidence=ConfidenceValue.impossible(),
            )
        return QueryOutput(
            query_text=query_text,
            results=[{}],   # bool query — no bindings exposed to user
            confidence=disjoin_all(all_confidences),
        )

    def _exec_find_query(self, query: FindQuery) -> QueryOutput:
        var_names = [v.name for v in query.variables]
        query_text = f"find {', '.join(var_names)} where ..."

        from logos.inference import _compare

        # Group proofs by their binding tuple; OR-combine confidences per group.
        # This correctly handles multiple derivation paths for the same result.
        groups: dict[tuple, list[ConfidenceValue]] = {}
        for proof in self.engine.prove_all(query.conditions):
            if not proof.success:
                continue
            if query.confidence_filter:
                op, threshold = query.confidence_filter
                if not _compare(proof.confidence.point, op, threshold):
                    continue
            key = tuple(proof.bindings.get(v) for v in var_names)
            groups.setdefault(key, []).append(proof.confidence)

        results = []
        for key, confidences in groups.items():
            combined = disjoin_all(confidences)
            row = dict(zip(var_names, key))
            row["__confidence__"] = combined
            results.append(row)

        best_conf = (max((r["__confidence__"] for r in results),
                         key=lambda c: c.point)
                     if results else ConfidenceValue.impossible())
        return QueryOutput(
            query_text=query_text,
            results=results,
            confidence=best_conf,
        )

    # ── Direct query API (for tests) ──────────────────────────────────────────

    def query(self, predicate_name: str, *args) -> QueryOutput:
        """Programmatic query: executor.query('can-vote', 'alice')"""
        pred = PredicateCall(
            name=predicate_name,
            args=list(args),
        )
        return self._exec_bool_query(BoolQuery(predicate=pred))

    def find(self, var_name: str, predicate_name: str, *args) -> set:
        """Programmatic find: executor.find('P', 'can-vote', Variable('P'))"""
        from logos.ast_nodes import Variable
        var = Variable(name=var_name)
        pred = PredicateCall(name=predicate_name, args=list(args) or [var])
        query = FindQuery(variables=[var], conditions=[pred])
        output = self._exec_find_query(query)
        return {r[var_name] for r in output.results if r.get(var_name) is not None}

    # ── Import ────────────────────────────────────────────────────────────────

    def _exec_import(self, stmt: ImportStmt):
        resolved = self._resolve_import(stmt.source)
        if resolved is None:
            raise err.LogosImportError(f"Cannot find import: {stmt.source!r}")
        self.load_file(resolved)

    def _resolve_import(self, source: str) -> Optional[str]:
        for base in self.search_path:
            candidate = os.path.join(base, source)
            if os.path.exists(candidate):
                return candidate
            if not candidate.endswith(".logos"):
                candidate += ".logos"
                if os.path.exists(candidate):
                    return candidate
        return None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _apply_op(left: Any, op: str, right: Any) -> Any:
    from logos.ast_nodes import DurationLit
    if isinstance(left, DurationLit) and isinstance(right, DurationLit):
        ls, rs = left.to_seconds(), right.to_seconds()
        if op == "+": return DurationLit(ls + rs, "seconds")
        if op == "-": return DurationLit(ls - rs, "seconds")
    try:
        if op == "+": return left + right
        if op == "-": return left - right
        if op == "*": return left * right
        if op == "/": return left / right
    except (TypeError, ZeroDivisionError):
        pass
    return None


def run_file(path: str) -> Executor:
    """Convenience: load a file and return the executor for further queries."""
    ex = Executor(search_path=[os.path.dirname(path)])
    ex.load_file(path)
    return ex


def run_source(source: str) -> Executor:
    """Convenience: run source string and return executor."""
    ex = Executor()
    ex.load_source(source)
    return ex
