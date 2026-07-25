from __future__ import annotations

from collections import namedtuple

from audit_mechanical_mbo_handoff import apply_packet


Event = namedtuple("Event", "action order_id side price size")


def test_state_lifecycle_uses_cancel_as_fill_mutation() -> None:
    state = {}
    apply_packet([Event("A", 1, "B", 100.0, 10)], state)
    apply_packet(
        [
            Event("F", 1, "B", 100.0, 4),
            Event("C", 1, "B", 100.0, 4),
        ],
        state,
    )
    assert state[1] == ("B", 100.0, 6.0)
    apply_packet([Event("M", 1, "B", 100.25, 8)], state)
    assert state[1] == ("B", 100.25, 8.0)
    apply_packet([Event("C", 1, "B", 100.25, 8)], state)
    assert 1 not in state
