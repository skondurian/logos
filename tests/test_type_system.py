"""Tests for the type system and TypeLattice."""

import pytest
from hypothesis import given, strategies as st

from logos.type_system import TypeLattice, OntologicalType
from logos.ast_nodes import TypeDecl, FieldDecl, TypeExpr


def make_lattice():
    return TypeLattice()


# ─── Built-in types ───────────────────────────────────────────────────────────

def test_builtins_exist():
    lat = make_lattice()
    for name in ["Entity", "Number", "Integer", "Float", "Text",
                 "Boolean", "Duration", "Set", "List"]:
        assert lat.exists(name), f"Built-in {name!r} missing"

def test_duration_is_number():
    lat = make_lattice()
    assert lat.is_subtype_of("Duration", "Number")
    assert lat.is_subtype_of("Duration", "Entity")

def test_integer_is_number():
    lat = make_lattice()
    assert lat.is_subtype_of("Integer", "Number")

def test_text_is_entity():
    lat = make_lattice()
    assert lat.is_subtype_of("Text", "Entity")
    assert not lat.is_subtype_of("Text", "Number")

def test_reflexive():
    lat = make_lattice()
    assert lat.is_subtype_of("Duration", "Duration")
    assert lat.is_subtype_of("Entity", "Entity")


# ─── User-defined types ───────────────────────────────────────────────────────

def test_register_simple_type():
    lat = make_lattice()
    decl = TypeDecl(name="Animal", parents=["Entity"], fields=[])
    lat.register(decl)
    assert lat.exists("Animal")
    assert lat.is_subtype_of("Animal", "Entity")

def test_register_type_with_parent():
    lat = make_lattice()
    lat.register(TypeDecl(name="Animal", parents=["Entity"], fields=[]))
    lat.register(TypeDecl(name="Dog", parents=["Animal"], fields=[]))
    assert lat.is_subtype_of("Dog", "Animal")
    assert lat.is_subtype_of("Dog", "Entity")
    assert not lat.is_subtype_of("Animal", "Dog")

def test_transitivity():
    lat = make_lattice()
    lat.register(TypeDecl(name="A", parents=["Entity"], fields=[]))
    lat.register(TypeDecl(name="B", parents=["A"], fields=[]))
    lat.register(TypeDecl(name="C", parents=["B"], fields=[]))
    assert lat.is_subtype_of("C", "A")
    assert lat.is_subtype_of("C", "Entity")
    assert not lat.is_subtype_of("A", "C")

def test_multiple_inheritance():
    lat = make_lattice()
    lat.register(TypeDecl(name="Flyable", parents=["Entity"], fields=[]))
    lat.register(TypeDecl(name="Swimmable", parents=["Entity"], fields=[]))
    lat.register(TypeDecl(name="Duck", parents=["Flyable", "Swimmable"], fields=[]))
    assert lat.is_subtype_of("Duck", "Flyable")
    assert lat.is_subtype_of("Duck", "Swimmable")
    assert lat.is_subtype_of("Duck", "Entity")

def test_unknown_parent_raises():
    lat = make_lattice()
    with pytest.raises(Exception):
        lat.register(TypeDecl(name="Foo", parents=["NonExistent"], fields=[]))


# ─── Field inheritance ────────────────────────────────────────────────────────

def test_own_fields():
    lat = make_lattice()
    fields = [FieldDecl(name="name", type_expr=TypeExpr(name="HumanName"))]
    lat.register(TypeDecl(name="Person", parents=["Entity"], fields=fields))
    all_fields = lat.all_fields("Person")
    assert "name" in all_fields
    assert all_fields["name"].defined_on == "Person"

def test_inherited_fields():
    lat = make_lattice()
    lat.register(TypeDecl(
        name="Animal", parents=["Entity"],
        fields=[FieldDecl(name="species", type_expr=TypeExpr(name="Text"))]
    ))
    lat.register(TypeDecl(
        name="Dog", parents=["Animal"],
        fields=[FieldDecl(name="breed", type_expr=TypeExpr(name="Text"))]
    ))
    fields = lat.all_fields("Dog")
    assert "species" in fields
    assert "breed" in fields
    assert fields["species"].defined_on == "Animal"
    assert fields["breed"].defined_on == "Dog"

def test_own_field_shadows_inherited():
    lat = make_lattice()
    lat.register(TypeDecl(
        name="A", parents=["Entity"],
        fields=[FieldDecl(name="x", type_expr=TypeExpr(name="Integer"))]
    ))
    lat.register(TypeDecl(
        name="B", parents=["A"],
        fields=[FieldDecl(name="x", type_expr=TypeExpr(name="Float"))]
    ))
    fields = lat.all_fields("B")
    assert fields["x"].type_expr.name == "Float"
    assert fields["x"].defined_on == "B"


# ─── Ancestor queries ─────────────────────────────────────────────────────────

def test_ancestors():
    lat = make_lattice()
    lat.register(TypeDecl(name="A", parents=["Entity"], fields=[]))
    lat.register(TypeDecl(name="B", parents=["A"], fields=[]))
    anc = lat.ancestors("B")
    assert "A" in anc
    assert "Entity" in anc
    assert "B" not in anc

def test_lca():
    lat = make_lattice()
    lat.register(TypeDecl(name="Animal", parents=["Entity"], fields=[]))
    lat.register(TypeDecl(name="Dog", parents=["Animal"], fields=[]))
    lat.register(TypeDecl(name="Cat", parents=["Animal"], fields=[]))
    lca = lat.lca("Dog", "Cat")
    assert lca == "Animal"


# ─── Property-based: transitivity ─────────────────────────────────────────────

@given(
    chain=st.lists(st.text(alphabet=st.characters(
        whitelist_categories=("Lu",)), min_size=1, max_size=8),
        min_size=2, max_size=6, unique=True)
)
def test_transitivity_property(chain):
    """If A < B < C < ... < Z, then A IS-A every type in the chain."""
    lat = make_lattice()
    # Prepend "E" so chain starts from a valid builtin
    names = ["Ep" + n for n in chain]
    for i, name in enumerate(names):
        parent = names[i - 1] if i > 0 else "Entity"
        lat.register(TypeDecl(name=name, parents=[parent], fields=[]))
    # Each type is a subtype of all earlier (less derived) types
    # names[j] extends names[j-1], so names[j] IS-A names[i] for j >= i
    for i in range(len(names)):
        for j in range(i, len(names)):
            assert lat.is_subtype_of(names[j], names[i])
