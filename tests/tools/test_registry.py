"""Registry smoke test — proves all pillar tool modules import cleanly, tool names
are globally unique (registry raises on a duplicate), and specs build."""

from __future__ import annotations

from tools.registry import MUTATING, PILLAR_OF, SPECS, TOOLS_BY_NAME


def test_registry_loads_unique_tools():
    assert TOOLS_BY_NAME, "no tools registered"
    assert len(SPECS) == len(TOOLS_BY_NAME)
    assert MUTATING <= set(TOOLS_BY_NAME), "a mutating name isn't a real tool"
    assert set(PILLAR_OF) == set(TOOLS_BY_NAME)


def test_reference_tool_registered():
    assert "sign_equipment" in TOOLS_BY_NAME
    assert "sign_equipment" in MUTATING
    assert PILLAR_OF["sign_equipment"] == "logistics"


def test_specs_have_names_and_params():
    for spec in SPECS:
        assert spec["name"] and "parameters" in spec
        assert "ctx" not in spec["parameters"]["properties"]  # ctx is never exposed
