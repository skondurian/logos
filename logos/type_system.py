"""
Type system for Logos — TypeLattice backed by networkx.

Supports:
  - IS-A multiple inheritance lattice
  - Subtype checking via ancestor closure
  - Field inheritance (fields defined on parents propagate to children)
  - Built-in primitive types

The lattice root is Entity. All user-defined types implicitly extend Entity
unless they specify explicit parents.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx

from logos.ast_nodes import TypeDecl, TypeExpr, FieldDecl
from logos import errors as err


# ─── Field descriptor ─────────────────────────────────────────────────────────

@dataclass
class FieldInfo:
    name: str
    type_expr: TypeExpr
    defined_on: str  # type name where the field was originally declared


# ─── Ontological type ────────────────────────────────────────────────────────

@dataclass
class OntologicalType:
    name: str
    parents: list[str] = field(default_factory=list)
    own_fields: list[FieldDecl] = field(default_factory=list)
    builtin: bool = False

    def __repr__(self) -> str:
        if self.parents:
            return f"Type({self.name} < {', '.join(self.parents)})"
        return f"Type({self.name})"


# ─── Type lattice ─────────────────────────────────────────────────────────────

class TypeLattice:
    """
    A directed acyclic graph of OntologicalTypes.

    Edges go FROM child TO parent (IS-A direction), consistent with
    networkx ancestor semantics: ancestors(child) returns all supertypes.
    """

    def __init__(self):
        self._graph: nx.DiGraph = nx.DiGraph()
        self._types: dict[str, OntologicalType] = {}
        self._bootstrap()

    def _bootstrap(self):
        """Register built-in primitive types."""
        builtins = [
            OntologicalType("Entity",   builtin=True),
            OntologicalType("Number",   parents=["Entity"], builtin=True),
            OntologicalType("Integer",  parents=["Number"], builtin=True),
            OntologicalType("Float",    parents=["Number"], builtin=True),
            OntologicalType("Text",     parents=["Entity"], builtin=True),
            OntologicalType("HumanName",parents=["Text"],  builtin=True),
            OntologicalType("Boolean",  parents=["Entity"], builtin=True),
            OntologicalType("Duration", parents=["Number"], builtin=True),
            OntologicalType("Timestamp",parents=["Entity"], builtin=True),
            OntologicalType("GeoLocation", parents=["Entity"], builtin=True),
            OntologicalType("URL",      parents=["Text"],  builtin=True),
            OntologicalType("Set",      parents=["Entity"], builtin=True),
            OntologicalType("List",     parents=["Entity"], builtin=True),
            OntologicalType("Optional", parents=["Entity"], builtin=True),
        ]
        for t in builtins:
            self._register_type(t)

    def _register_type(self, ot: OntologicalType):
        self._types[ot.name] = ot
        self._graph.add_node(ot.name)
        for parent in ot.parents:
            if parent not in self._graph:
                self._graph.add_node(parent)
            self._graph.add_edge(ot.name, parent)

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, decl: TypeDecl) -> OntologicalType:
        """Register a user-defined type from a TypeDecl AST node."""
        parents = decl.parents if decl.parents else ["Entity"]
        for p in parents:
            if p not in self._types:
                raise err.TypeError(
                    f"Type '{decl.name}' extends unknown type '{p}'"
                )
        ot = OntologicalType(
            name=decl.name,
            parents=parents,
            own_fields=decl.fields,
        )
        if decl.name in self._types and not self._types[decl.name].builtin:
            # Redefinition — merge fields
            existing = self._types[decl.name]
            existing.own_fields.extend(decl.fields)
            return existing
        self._register_type(ot)
        return ot

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[OntologicalType]:
        return self._types.get(name)

    def exists(self, name: str) -> bool:
        return name in self._types

    def is_subtype_of(self, child: str, parent: str) -> bool:
        """Return True if child IS-A parent (reflexive)."""
        if child == parent:
            return True
        if child not in self._graph or parent not in self._graph:
            return False
        try:
            return nx.has_path(self._graph, child, parent)
        except nx.NetworkXError:
            return False

    def ancestors(self, name: str) -> set[str]:
        """Return all supertypes of name (excluding itself).

        Edges go child→parent, so supertypes are reachable via nx.descendants.
        """
        if name not in self._graph:
            return set()
        return set(nx.descendants(self._graph, name))

    def all_fields(self, name: str) -> dict[str, FieldInfo]:
        """
        Return all fields visible on type `name`, including inherited ones.
        Own fields take precedence over inherited fields of the same name.
        """
        if name not in self._types:
            return {}
        # Traverse ancestors in topological order (BFS from name toward Entity)
        result: dict[str, FieldInfo] = {}
        visited = set()
        queue = [name]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            ot = self._types.get(current)
            if ot is None:
                continue
            # Own fields have lowest BFS distance → highest priority
            for f in ot.own_fields:
                if f.name not in result:
                    result[f.name] = FieldInfo(
                        name=f.name,
                        type_expr=f.type_expr,
                        defined_on=current,
                    )
            queue.extend(ot.parents)
        return result

    def check_type_expr(self, expr: TypeExpr) -> bool:
        """Return True if the TypeExpr refers to known types."""
        if not self.exists(expr.name):
            return False
        return all(self.check_type_expr(p) for p in expr.params)

    def lca(self, a: str, b: str) -> Optional[str]:
        """Least common ancestor in the type lattice."""
        if a not in self._graph or b not in self._graph:
            return None
        a_anc = {a} | self.ancestors(a)
        b_anc = {b} | self.ancestors(b)
        common = a_anc & b_anc
        if not common:
            return None
        # Most specific common ancestor = deepest = most ancestors of its own.
        return max(common, key=lambda n: len(self.ancestors(n)))

    def all_type_names(self) -> list[str]:
        return list(self._types.keys())
