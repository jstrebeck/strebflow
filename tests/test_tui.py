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
