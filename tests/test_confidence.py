"""Tests for confidence arithmetic."""

import pytest
from hypothesis import given, strategies as st
from logos.confidence import (
    ConfidenceValue, conjoin_all, disjoin_all, from_annotation
)


# ─── Basic construction ───────────────────────────────────────────────────────

def test_absolute():
    cv = ConfidenceValue.absolute()
    assert cv.point == 1.0
    assert cv.lower == 1.0
    assert cv.upper == 1.0
    assert cv.is_certain()

def test_impossible():
    cv = ConfidenceValue.impossible()
    assert cv.point == 0.0
    assert cv.is_impossible()

def test_from_point():
    cv = ConfidenceValue.from_point(0.7)
    assert abs(cv.point - 0.7) < 1e-6
    assert 0.0 <= cv.lower <= cv.point <= cv.upper <= 1.0

def test_from_interval():
    cv = ConfidenceValue.from_interval(0.6, 0.9)
    assert cv.point == pytest.approx(0.75, abs=0.01)
    assert 0.0 <= cv.lower <= cv.upper <= 1.0


# ─── Arithmetic invariants ────────────────────────────────────────────────────

def test_conjunction_le_min():
    a = ConfidenceValue.from_point(0.8)
    b = ConfidenceValue.from_point(0.6)
    c = a.conjoin(b)
    assert c.point <= min(a.point, b.point) + 1e-9

def test_disjunction_ge_max():
    a = ConfidenceValue.from_point(0.8)
    b = ConfidenceValue.from_point(0.6)
    d = a.disjoin(b)
    assert d.point >= max(a.point, b.point) - 1e-9

def test_conjunction_with_absolute():
    a = ConfidenceValue.from_point(0.7)
    b = ConfidenceValue.absolute()
    assert a.conjoin(b).point == pytest.approx(0.7, abs=1e-6)

def test_disjunction_with_impossible():
    a = ConfidenceValue.from_point(0.7)
    b = ConfidenceValue.impossible()
    assert a.disjoin(b).point == pytest.approx(0.7, abs=1e-6)

def test_bounds_never_outside_01():
    for p in [0.0, 0.1, 0.5, 0.9, 1.0]:
        cv = ConfidenceValue.from_point(p)
        assert 0.0 <= cv.lower <= cv.upper <= 1.0

def test_degradation_reduces():
    cv = ConfidenceValue.from_point(0.9)
    degraded = cv.degrade(0.95)
    assert degraded.point < cv.point

def test_degradation_stays_in_range():
    cv = ConfidenceValue.from_point(0.5)
    degraded = cv.degrade(0.8)
    assert 0.0 <= degraded.point <= 1.0


# ─── Property-based tests ─────────────────────────────────────────────────────

@given(
    a=st.floats(min_value=0.01, max_value=0.99),
    b=st.floats(min_value=0.01, max_value=0.99),
)
def test_conjunction_commutativity(a, b):
    ca = ConfidenceValue.from_point(a)
    cb = ConfidenceValue.from_point(b)
    assert abs(ca.conjoin(cb).point - cb.conjoin(ca).point) < 1e-9

@given(
    a=st.floats(min_value=0.01, max_value=0.99),
    b=st.floats(min_value=0.01, max_value=0.99),
)
def test_disjunction_commutativity(a, b):
    ca = ConfidenceValue.from_point(a)
    cb = ConfidenceValue.from_point(b)
    assert abs(ca.disjoin(cb).point - cb.disjoin(ca).point) < 1e-9

@given(
    a=st.floats(min_value=0.01, max_value=0.99),
    b=st.floats(min_value=0.01, max_value=0.99),
    c=st.floats(min_value=0.01, max_value=0.99),
)
def test_conjunction_associativity(a, b, c):
    ca = ConfidenceValue.from_point(a)
    cb = ConfidenceValue.from_point(b)
    cc = ConfidenceValue.from_point(c)
    left = ca.conjoin(cb).conjoin(cc)
    right = ca.conjoin(cb.conjoin(cc))
    assert abs(left.point - right.point) < 1e-6


# ─── Reduction ────────────────────────────────────────────────────────────────

def test_conjoin_all_empty():
    assert conjoin_all([]).is_certain()

def test_disjoin_all_empty():
    assert disjoin_all([]).is_impossible()

def test_conjoin_all_single():
    cv = ConfidenceValue.from_point(0.7)
    assert conjoin_all([cv]).point == pytest.approx(0.7, abs=1e-6)


# ─── Annotation parsing ───────────────────────────────────────────────────────

def test_from_annotation_absolute():
    assert from_annotation("absolute").is_certain()

def test_from_annotation_float():
    cv = from_annotation(0.8)
    assert abs(cv.point - 0.8) < 1e-6

def test_from_annotation_interval():
    cv = from_annotation((0.6, 0.9))
    assert 0.5 <= cv.point <= 1.0
