"""Shared pytest fixtures.

Provides an in-memory, seeded SQLite database that is fully isolated per test
(DESIGN.md §12 test isolation). No file is touched and nothing leaks between tests.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from faker import Faker

# Make the project root importable (models, rules, scripts, ...).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.db import create_all, create_session, get_engine
from scripts.generate_data import generate


@pytest.fixture
def session():
    """A fresh in-memory DB seeded with a small, deterministic, valid dataset."""
    random.seed(0)
    Faker.seed(0)
    engine = get_engine(":memory:")
    create_all(engine)
    s = create_session(engine)
    generate(s, 12, Faker())
    s.commit()
    try:
        yield s
    finally:
        s.close()
