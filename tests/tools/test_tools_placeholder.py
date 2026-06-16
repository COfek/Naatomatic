"""Placeholder for hard-coded tool-call tests (no model in the loop).

Pattern (once tools/ exists): call a tool with fixed args against the `session`
fixture and assert BOTH paths:
  - accept path: a valid action succeeds and the DB reflects the change
  - reject path: an action that breaks a hard rule is blocked and the DB is unchanged

Example shape:
    def test_sign_third_monitor_is_rejected(session):
        # arrange: a person already holding 2 monitors
        # act: logistics_tools.sign_equipment(session, monitor3, person)
        # assert: result.ok is False and the item is still unsigned (HC-LOG-1)
"""

import pytest


@pytest.mark.skip(reason="tools/ layer not built yet — template placeholder")
def test_tool_accept_and_reject_paths():
    ...
