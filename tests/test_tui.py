"""Tests for the pipeline TUI display."""
from __future__ import annotations

import time

import pytest

from rich.panel import Panel
from rich.text import Text

from attractor.tui import (
    BranchTarget,
    PipelineDisplay,
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

    def test_on_cycle_start_does_not_reset_active_stage(self):
        """CYCLE_START fires from inside implementer — don't reset it."""
        self.display.on_node_enter("implementer")
        self.display.on_cycle_start(1)
        assert self.display.stages["implementer"].status == StageStatus.ACTIVE

    def test_done_after_convergence_does_not_mark_validator_failed(self):
        """On success path, done entry should not mark validator as FAILED."""
        self.display.on_node_enter("scenario_validator")
        self.display.on_node_exit("scenario_validator")
        self.display.on_convergence()
        self.display.on_node_enter("done")
        assert self.display.stages["scenario_validator"].status == StageStatus.COMPLETED


class TestMainRowRendering:
    def setup_method(self):
        self.display = PipelineDisplay(max_cycles=3)

    def test_main_row_contains_all_main_path_labels(self):
        row, _ = self.display._render_main_row()
        plain = row.plain
        for node_name in self.display.topology.main_path:
            label = self.display.stages[node_name].label
            assert label in plain, f"{label} not in main row"

    def test_main_row_does_not_contain_diagnoser(self):
        row, _ = self.display._render_main_row()
        assert "Diagnose" not in row.plain

    def test_main_row_has_branch_column(self):
        _, branch_col = self.display._render_main_row()
        assert branch_col > 0

    def test_main_row_has_branch_connector(self):
        row, _ = self.display._render_main_row()
        assert "┬" in row.plain

    def test_stage_positions_match_main_row(self):
        """Column positions should correspond to actual character offsets."""
        positions = self.display._compute_stage_positions()
        row, _ = self.display._render_main_row()
        plain = row.plain
        for node_name in self.display.topology.main_path:
            col = positions[node_name]
            label = self.display.stages[node_name].label
            # The label starts at col + 2 (icon + space)
            assert plain[col + 2:col + 2 + len(label)] == label


class TestCustomTopology:
    def test_linear_pipeline_no_branches(self):
        topo = PipelineTopology(
            stages=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
            main_path=["a", "b", "c"],
            branch_points={},
            cycle_resettable=set(),
        )
        display = PipelineDisplay(max_cycles=1, topology=topo)
        row, branch_col = display._render_main_row()
        assert "Alpha" in row.plain
        assert "Beta" in row.plain
        assert "Gamma" in row.plain
        assert branch_col == -1


class TestBranchTreeRendering:
    def setup_method(self):
        self.display = PipelineDisplay(max_cycles=3)

    def test_branch_tree_contains_diagnose(self):
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_branch_tree(branch_col)
        text = "\n".join(line.plain for line in lines)
        assert "Diagnose" in text

    def test_branch_tree_contains_back_edge(self):
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_branch_tree(branch_col)
        text = "\n".join(line.plain for line in lines)
        assert "Implement" in text

    def test_branch_tree_shows_exhausted(self):
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_branch_tree(branch_col)
        text = "\n".join(line.plain for line in lines)
        assert "exhausted" in text

    def test_branch_tree_has_connectors(self):
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_branch_tree(branch_col)
        text = "\n".join(line.plain for line in lines)
        assert "├" in text
        assert "╰" in text
        assert "│" in text

    def test_no_branch_tree_for_linear_topology(self):
        topo = PipelineTopology(
            stages=[("a", "Alpha"), ("b", "Beta")],
            main_path=["a", "b"],
            branch_points={},
            cycle_resettable=set(),
        )
        display = PipelineDisplay(max_cycles=1, topology=topo)
        lines = display._render_branch_tree(-1)
        assert lines == []


class TestMetadataRendering:
    def setup_method(self):
        self.display = PipelineDisplay(max_cycles=3)

    def test_metadata_spacers_when_no_active(self):
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_metadata_lines(branch_col)
        assert len(lines) == 2  # always 2 lines for stable height

    def test_metadata_shows_elapsed_for_active(self):
        self.display.on_node_enter("planner")
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_metadata_lines(branch_col)
        assert len(lines) >= 1
        text = lines[0].plain
        assert "s" in text  # elapsed time contains "s"

    def test_metadata_shows_tool_calls_for_implementer(self):
        self.display.on_node_enter("implementer")
        self.display.on_tool_call()
        self.display.on_tool_call()
        self.display.on_tool_call()
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_metadata_lines(branch_col)
        text = "\n".join(line.plain for line in lines)
        assert "3 tool calls" in text


class TestFullRender:
    def test_render_returns_panel(self):
        display = PipelineDisplay(max_cycles=3)
        result = display._render()
        assert isinstance(result, Panel)

    def test_render_contains_branch_tree(self):
        display = PipelineDisplay(max_cycles=3)
        panel = display._render()
        # The panel's renderable is a Text object; check its plain content
        content = panel.renderable
        assert isinstance(content, Text)
        assert "Diagnose" in content.plain
        assert "Implement" in content.plain

    def test_render_with_active_stage(self):
        display = PipelineDisplay(max_cycles=3)
        display.on_node_enter("implementer")
        display.on_tool_call()
        panel = display._render()
        content = panel.renderable
        assert isinstance(content, Text)
        assert "tool calls" in content.plain

    def test_render_converged_border(self):
        display = PipelineDisplay(max_cycles=3)
        display.on_convergence()
        panel = display._render()
        assert panel.border_style == "green"
