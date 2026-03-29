"""Tests for the pipeline TUI display."""
from __future__ import annotations

import time

import pytest

from attractor.tui import (
    BranchTarget,
    PipelineTopology,
    StageInfo,
    StageStatus,
    default_attractor_topology,
    format_elapsed,
)


class TestStageInfo:
    def test_default_status_is_pending(self):
        stage = StageInfo(name="test", label="Test")
        assert stage.status == StageStatus.PENDING

    def test_elapsed_zero_when_not_started(self):
        stage = StageInfo(name="test", label="Test")
        assert stage.elapsed == 0.0

    def test_elapsed_uses_end_time(self):
        stage = StageInfo(name="test", label="Test", start_time=100.0, end_time=105.5)
        assert stage.elapsed == pytest.approx(5.5)

    def test_elapsed_ticks_when_running(self):
        stage = StageInfo(name="test", label="Test", start_time=time.monotonic() - 2.0)
        assert stage.elapsed >= 2.0


class TestFormatElapsed:
    def test_seconds(self):
        assert format_elapsed(5.3) == "5.3s"

    def test_minutes(self):
        assert format_elapsed(125.7) == "2m 5.7s"

    def test_zero(self):
        assert format_elapsed(0.0) == "0.0s"


class TestDefaultTopology:
    def test_label_map(self):
        topo = default_attractor_topology()
        assert topo.label_map["spec_loader"] == "Specs"
        assert topo.label_map["implementer"] == "Implement"

    def test_main_path_excludes_diagnoser(self):
        topo = default_attractor_topology()
        assert "diagnoser" not in topo.main_path

    def test_branch_points(self):
        topo = default_attractor_topology()
        assert "scenario_validator" in topo.branch_points
        targets = topo.branch_points["scenario_validator"]
        assert len(targets) == 2
        assert targets[0].node == "diagnoser"
        assert targets[0].back_edge_to == "implementer"
        assert targets[1].node == "done"
        assert targets[1].condition_label == "exhausted"


from attractor.tui import PipelineDisplay


class TestEventHandlers:
    def setup_method(self):
        self.display = PipelineDisplay(max_cycles=3)

    def test_on_node_enter_sets_active(self):
        self.display.on_node_enter("planner")
        stage = self.display.stages["planner"]
        assert stage.status == StageStatus.ACTIVE
        assert stage.start_time is not None

    def test_on_node_enter_resets_implementer_tool_calls(self):
        self.display.on_node_enter("implementer")
        assert self.display.stages["implementer"].metadata["tool_calls"] == 0

    def test_on_node_enter_marks_branch_point_failed(self):
        """When diagnoser enters, scenario_validator should be retroactively marked FAILED."""
        self.display.on_node_enter("scenario_validator")
        self.display.on_node_exit("scenario_validator")
        self.display.on_node_enter("diagnoser")
        assert self.display.stages["scenario_validator"].status == StageStatus.FAILED

    def test_on_node_exit_sets_completed(self):
        self.display.on_node_enter("planner")
        self.display.on_node_exit("planner")
        assert self.display.stages["planner"].status == StageStatus.COMPLETED
        assert self.display.stages["planner"].end_time is not None

    def test_on_node_exit_sets_failed_on_error(self):
        self.display.on_node_enter("planner")
        self.display.on_node_exit("planner", error="boom")
        assert self.display.stages["planner"].status == StageStatus.FAILED

    def test_on_cycle_start_resets_cycle_nodes(self):
        self.display.on_node_enter("implementer")
        self.display.on_node_exit("implementer")
        assert self.display.stages["implementer"].status == StageStatus.COMPLETED
        self.display.on_cycle_start(1)
        assert self.display.stages["implementer"].status == StageStatus.PENDING
        assert self.display.stages["implementer"].start_time is None

    def test_on_cycle_start_preserves_non_cycle_nodes(self):
        self.display.on_node_enter("spec_loader")
        self.display.on_node_exit("spec_loader")
        self.display.on_cycle_start(1)
        assert self.display.stages["spec_loader"].status == StageStatus.COMPLETED

    def test_on_tool_call_increments(self):
        self.display.on_node_enter("implementer")
        self.display.on_tool_call()
        self.display.on_tool_call()
        assert self.display.stages["implementer"].metadata["tool_calls"] == 2

    def test_on_convergence(self):
        self.display.on_convergence()
        assert self.display.converged is True

    def test_unknown_node_ignored(self):
        self.display.on_node_enter("nonexistent")  # should not raise
        self.display.on_node_exit("nonexistent")
