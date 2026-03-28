import pytest
from attractor.graph import route_after_validation

def test_route_passes_to_reviewer():
    state = {"validation_result": {"passed": True}, "cycle": 0, "max_cycles": 10}
    assert route_after_validation(state) == "reviewer"

def test_route_fails_to_diagnoser():
    state = {"validation_result": {"passed": False}, "cycle": 0, "max_cycles": 10}
    assert route_after_validation(state) == "diagnoser"

def test_route_exhausted_to_done():
    state = {"validation_result": {"passed": False}, "cycle": 10, "max_cycles": 10}
    assert route_after_validation(state) == "done"
