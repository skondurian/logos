"""Shared pytest fixtures."""
import pathlib
import pytest

@pytest.fixture
def examples_dir():
    return pathlib.Path(__file__).parent.parent / "examples"

@pytest.fixture
def fixtures_dir():
    return pathlib.Path(__file__).parent / "fixtures"
