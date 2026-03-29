# Pipeline TUI — DAG Topology Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the text-checklist pipeline TUI with an animated DAG topology display showing branches, retry loops, per-stage elapsed times, and tool call counts.

**Architecture:** Full rewrite of `src/attractor/tui.py` (~280 lines). Data-driven topology: stages, edges, and branch points defined as dataclasses, not hardcoded rendering templates. Rendering builds Rich `Text` objects line-by-line for character-level control. Event handler API is unchanged — zero changes to callers.

**Tech Stack:** Python 3.12+, Rich 13.0+ (existing dependency), structlog (unchanged)

**Spec:** `docs/superpowers/specs/2026-03-28-pipeline-tui-dag-design.md`

**Scope note:** Narrow-terminal fallback (wrapping at <100 chars) is deferred. The initial build targets 110+ char terminals. Rich handles overflow gracefully at smaller widths.

---

### File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/attractor/tui.py` | Full rewrite | Data models, topology, rendering engine, event handlers |
| `tests/test_tui.py` | Create | Tests for data models, state management, rendering |
| `demo_tui.py` | Create | Standalone demo simulating all 8 stages with retry |

**Files NOT changed:** `logging.py`, `graph.py`, `__main__.py`, any node files.

---

### Task 1: Data Models and Helpers

**Files:**
- Create: `tests/test_tui.py` (initial test scaffolding)
- Create: `src/attractor/tui.py` (data models only — replaces existing file)

- [ ] **Step 1: Write failing tests for data models**

```python
# tests/test_tui.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py -v`
Expected: ImportError — the new classes don't exist yet.

- [ ] **Step 3: Write the data models**

Replace `src/attractor/tui.py` entirely with:

```python
"""Terminal UI for the attractor pipeline — animated DAG topology display."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text


# ── Data Models ─────────────────────────────────────────────────────────

class StageStatus(Enum):
    PENDING = auto()
    ACTIVE = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class StageInfo:
    name: str
    label: str
    status: StageStatus = StageStatus.PENDING
    start_time: float | None = None
    end_time: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time is not None else time.monotonic()
        return end - self.start_time


@dataclass
class BranchTarget:
    """A branch off the main path at a branch point."""
    node: str
    back_edge_to: str | None = None
    condition_label: str | None = None


@dataclass
class PipelineTopology:
    """Defines the pipeline DAG structure."""
    stages: list[tuple[str, str]]
    main_path: list[str]
    branch_points: dict[str, list[BranchTarget]]
    cycle_resettable: set[str]

    @property
    def label_map(self) -> dict[str, str]:
        return dict(self.stages)


def default_attractor_topology() -> PipelineTopology:
    return PipelineTopology(
        stages=[
            ("spec_loader", "Specs"),
            ("planner", "Plan"),
            ("implementer", "Implement"),
            ("test_runner", "Test"),
            ("scenario_validator", "Validate"),
            ("diagnoser", "Diagnose"),
            ("reviewer", "Review"),
            ("done", "Done"),
        ],
        main_path=[
            "spec_loader", "planner", "implementer", "test_runner",
            "scenario_validator", "reviewer", "done",
        ],
        branch_points={
            "scenario_validator": [
                BranchTarget(node="diagnoser", back_edge_to="implementer"),
                BranchTarget(node="done", condition_label="exhausted"),
            ],
        },
        cycle_resettable={"implementer", "test_runner", "scenario_validator", "diagnoser"},
    )


# ── Formatting Helpers ──────────────────────────────────────────────────

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_ICON_MAP = {
    StageStatus.PENDING: ("·", "dim"),
    StageStatus.COMPLETED: ("✓", "green"),
    StageStatus.FAILED: ("✗", "red"),
}

_LABEL_STYLES = {
    StageStatus.PENDING: "dim",
    StageStatus.ACTIVE: "bold cyan",
    StageStatus.COMPLETED: "green",
    StageStatus.FAILED: "red",
}


def format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    return f"{minutes}m {secs:.1f}s"
```

This is a partial file — it contains only the data models and helpers. The `PipelineDisplay` class will be added in subsequent tasks. Note: this will temporarily break the existing `from attractor.tui import PipelineDisplay` import in `logging.py` and `__main__.py`. That's expected — the class is rebuilt in Task 2.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/attractor/tui.py tests/test_tui.py
git commit -m "feat(tui): add data models for DAG topology display

StageStatus enum, StageInfo dataclass with elapsed timer,
PipelineTopology with branch points, and default attractor topology."
```

---

### Task 2: PipelineDisplay State Management

**Files:**
- Modify: `tests/test_tui.py` (add event handler tests)
- Modify: `src/attractor/tui.py` (add PipelineDisplay class with event handlers)

- [ ] **Step 1: Write failing tests for event handlers**

Append to `tests/test_tui.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py::TestEventHandlers -v`
Expected: ImportError — `PipelineDisplay` doesn't exist yet.

- [ ] **Step 3: Write PipelineDisplay with event handlers**

Append to `src/attractor/tui.py` (after the `format_elapsed` function):

```python
# ── PipelineDisplay ─────────────────────────────────────────────────────

class PipelineDisplay:
    """Live terminal display showing pipeline DAG topology with animation."""

    def __init__(
        self,
        max_cycles: int = 10,
        topology: PipelineTopology | None = None,
    ) -> None:
        self.console = Console()
        self.max_cycles = max_cycles
        self.topology = topology or default_attractor_topology()
        self.cycle = 0
        self.converged = False
        self._live: Live | None = None
        self._frame = 0

        self.stages: dict[str, StageInfo] = {
            name: StageInfo(name=name, label=label)
            for name, label in self.topology.stages
        }

        # Map branch targets to their branch point node so entering a branch
        # target retroactively marks the branch point as FAILED (visual cue
        # that the branch was taken, e.g. diagnoser entered → validate "failed").
        self._branch_failure_map: dict[str, str] = {}
        for bp_node, targets in self.topology.branch_points.items():
            for target in targets:
                self._branch_failure_map[target.node] = bp_node

    # ── Context manager ──────────────────────────────────────────────

    def start(self) -> None:
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=12,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.update(self._render())
            self._live.stop()
            self._live = None

    def __enter__(self) -> PipelineDisplay:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # ── Event handlers ───────────────────────────────────────────────

    def on_node_enter(self, node: str) -> None:
        if node in self.stages:
            stage = self.stages[node]
            stage.status = StageStatus.ACTIVE
            stage.start_time = time.monotonic()
            stage.end_time = None
            if node == "implementer":
                stage.metadata["tool_calls"] = 0
        if node in self._branch_failure_map:
            bp = self._branch_failure_map[node]
            if bp in self.stages:
                self.stages[bp].status = StageStatus.FAILED
        self._refresh()

    def on_node_exit(self, node: str, error: str | None = None) -> None:
        if node in self.stages:
            stage = self.stages[node]
            stage.status = StageStatus.FAILED if error else StageStatus.COMPLETED
            stage.end_time = time.monotonic()
        self._refresh()

    def on_cycle_start(self, cycle: int) -> None:
        self.cycle = cycle
        if cycle > 0:
            for name in self.topology.cycle_resettable:
                if name in self.stages:
                    stage = self.stages[name]
                    stage.status = StageStatus.PENDING
                    stage.start_time = None
                    stage.end_time = None
                    stage.metadata.clear()
        self._refresh()

    def on_tool_call(self) -> None:
        for stage in self.stages.values():
            if stage.status == StageStatus.ACTIVE and stage.name == "implementer":
                stage.metadata["tool_calls"] = stage.metadata.get("tool_calls", 0) + 1
        self._refresh()

    def on_convergence(self) -> None:
        self.converged = True
        self._refresh()

    # ── Log output ───────────────────────────────────────────────────

    def log(self, message: str) -> None:
        if self._live:
            self.console.print(Text.from_ansi(message))
        else:
            print(message)

    # ── Rendering (stub — filled in Task 3-5) ────────────────────────

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Panel:
        return Panel("(rendering not yet implemented)", border_style="blue")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py -v`
Expected: All 21 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/attractor/tui.py tests/test_tui.py
git commit -m "feat(tui): add PipelineDisplay with event handlers

State management for stage tracking, cycle resets, tool call counting,
convergence flag, and branch-failure retroactive marking."
```

---

### Task 3: Main Row Rendering

**Files:**
- Modify: `tests/test_tui.py` (add rendering tests)
- Modify: `src/attractor/tui.py` (add main row renderer)

- [ ] **Step 1: Write failing tests for main row rendering**

Append to `tests/test_tui.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py::TestMainRowRendering -v`
Expected: AttributeError — `_render_main_row` and `_compute_stage_positions` don't exist.

- [ ] **Step 3: Add main row rendering methods**

In `src/attractor/tui.py`, replace the rendering stub section with:

```python
    # ── Rendering ────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _spinner_char(self) -> str:
        self._frame = (self._frame + 1) % len(_SPINNER_FRAMES)
        return _SPINNER_FRAMES[self._frame]

    def _stage_icon(self, stage: StageInfo) -> tuple[str, str]:
        if stage.status == StageStatus.ACTIVE:
            return self._spinner_char(), "bold cyan"
        return _ICON_MAP[stage.status]

    def _render_main_row(self) -> tuple[Text, int]:
        """Build the main horizontal flow row.

        Returns (rendered_line, branch_column) where branch_column is the
        character offset of the branch connector, or -1 if no branch point.
        """
        line = Text()
        line.append("  ")
        branch_col = -1

        for i, node_name in enumerate(self.topology.main_path):
            stage = self.stages[node_name]
            icon, icon_style = self._stage_icon(stage)
            label_style = _LABEL_STYLES[stage.status]

            line.append(icon, style=icon_style)
            line.append(" ")
            line.append(stage.label, style=label_style)

            if i < len(self.topology.main_path) - 1:
                if node_name in self.topology.branch_points:
                    line.append(" ──", style="dim")
                    branch_col = len(line.plain)
                    line.append("┬", style="dim")
                    line.append("──→ ", style="dim")
                else:
                    line.append(" ──→ ", style="dim")

        return line, branch_col

    def _compute_stage_positions(self) -> dict[str, int]:
        """Compute the starting column of each stage on the main row."""
        positions = {}
        col = 2  # leading "  "

        for i, node_name in enumerate(self.topology.main_path):
            stage = self.stages[node_name]
            positions[node_name] = col
            col += 1 + 1 + len(stage.label)  # icon + space + label

            if i < len(self.topology.main_path) - 1:
                if node_name in self.topology.branch_points:
                    col += len(" ──┬──→ ")
                else:
                    col += len(" ──→ ")

        return positions

    def _render(self) -> Panel:
        """Assemble the full display panel (stub — branch tree added in Task 4)."""
        main_row, _ = self._render_main_row()
        border = "green" if self.converged else "blue"
        cycle_label = f"Cycle {self.cycle + 1} / {self.max_cycles}"
        return Panel(
            main_row,
            title="[bold]Attractor Pipeline[/bold]",
            subtitle=f"[dim]{cycle_label}[/dim]",
            border_style=border,
            padding=(1, 2),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/attractor/tui.py tests/test_tui.py
git commit -m "feat(tui): add main row rendering with DAG connectors

Horizontal flow row with status icons, labels, and branch connector
(┬) at the scenario_validator stage. Stage position tracking for
metadata alignment."
```

---

### Task 4: Branch Tree and Metadata Rendering

**Files:**
- Modify: `tests/test_tui.py` (add branch tree + metadata tests)
- Modify: `src/attractor/tui.py` (add branch tree + metadata renderers)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tui.py`:

```python
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

    def test_metadata_empty_when_no_active(self):
        _, branch_col = self.display._render_main_row()
        lines = self.display._render_metadata_lines(branch_col)
        assert len(lines) == 0

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py::TestBranchTreeRendering tests/test_tui.py::TestMetadataRendering -v`
Expected: AttributeError — `_render_branch_tree` and `_render_metadata_lines` don't exist.

- [ ] **Step 3: Add branch tree and metadata rendering methods**

In `src/attractor/tui.py`, add these methods to `PipelineDisplay` (between `_compute_stage_positions` and `_render`):

```python
    def _branch_connector_style(self, target_stage: StageInfo) -> str:
        """Style for branch connector lines — amber for diagnose path."""
        if target_stage.name == "diagnoser":
            if target_stage.status in (StageStatus.ACTIVE, StageStatus.COMPLETED):
                return "yellow"
        if target_stage.status == StageStatus.ACTIVE:
            return "cyan"
        if target_stage.status == StageStatus.COMPLETED:
            return "green"
        return "dim"

    def _render_metadata_lines(self, branch_col: int) -> list[Text]:
        """Render elapsed time and tool calls below the active main-path stage."""
        lines: list[Text] = []
        positions = self._compute_stage_positions()

        active: StageInfo | None = None
        for node_name in self.topology.main_path:
            stage = self.stages[node_name]
            if stage.status == StageStatus.ACTIVE:
                active = stage
                break

        if active is None:
            return lines

        col = positions.get(active.name, 0)
        elapsed_str = format_elapsed(active.elapsed)

        line = Text()
        line.append(" " * col)
        line.append(f"   {elapsed_str}", style="cyan")
        if branch_col > 0 and len(line.plain) < branch_col:
            line.append(" " * (branch_col - len(line.plain)))
            line.append("│", style="dim")
        lines.append(line)

        tool_calls = active.metadata.get("tool_calls", 0)
        if active.name == "implementer" and tool_calls > 0:
            tc_line = Text()
            tc_line.append(" " * col)
            tc_line.append(f"   {tool_calls} tool calls", style="dim cyan")
            if branch_col > 0 and len(tc_line.plain) < branch_col:
                tc_line.append(" " * (branch_col - len(tc_line.plain)))
                tc_line.append("│", style="dim")
            lines.append(tc_line)

        return lines

    def _render_branch_tree(self, branch_col: int) -> list[Text]:
        """Render the branch tree below the branch point."""
        if branch_col < 0:
            return []

        lines: list[Text] = []

        for _bp_node, targets in self.topology.branch_points.items():
            spacer = Text()
            spacer.append(" " * branch_col)
            spacer.append("│", style="dim")
            lines.append(spacer)

            for i, target in enumerate(targets):
                is_last = i == len(targets) - 1
                connector = "╰" if is_last else "├"

                stage = self.stages[target.node]
                icon, icon_style = self._stage_icon(stage)
                label_style = _LABEL_STYLES[stage.status]
                conn_style = self._branch_connector_style(stage)

                display_label = stage.label
                if target.condition_label:
                    display_label = f"{stage.label} ({target.condition_label})"

                line = Text()
                line.append(" " * branch_col)
                line.append(f"{connector}──→ ", style=conn_style)
                line.append(icon, style=icon_style)
                line.append(" ")
                line.append(display_label, style=label_style)
                lines.append(line)

                if target.back_edge_to:
                    back_label = self.topology.label_map[target.back_edge_to]
                    back_line = Text()
                    back_line.append(" " * branch_col)
                    back_line.append("│" if not is_last else " ", style="dim")
                    back_line.append("       ╰──→ ", style=conn_style)
                    back_line.append(back_label, style=conn_style)
                    lines.append(back_line)

                if not is_last:
                    s = Text()
                    s.append(" " * branch_col)
                    s.append("│", style="dim")
                    lines.append(s)

        return lines
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/attractor/tui.py tests/test_tui.py
git commit -m "feat(tui): add branch tree and metadata rendering

Branch tree with connectors, back-edge visualization, exhausted path.
Metadata lines show live elapsed time and tool call count below the
active stage. Amber/yellow styling for the diagnose retry path."
```

---

### Task 5: Full Panel Assembly and Integration

**Files:**
- Modify: `tests/test_tui.py` (add full render test)
- Modify: `src/attractor/tui.py` (wire up `_render` to assemble all pieces)

- [ ] **Step 1: Write failing test for full render**

Append to `tests/test_tui.py`:

```python
from rich.panel import Panel


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py::TestFullRender -v`
Expected: FAIL — current `_render` stub returns Panel with a string, not the full assembly.

- [ ] **Step 3: Update `_render` to assemble all pieces**

In `src/attractor/tui.py`, replace the `_render` method:

```python
    def _render(self) -> Panel:
        """Assemble the full DAG display panel."""
        lines: list[Text] = []

        main_row, branch_col = self._render_main_row()
        lines.append(main_row)

        lines.extend(self._render_metadata_lines(branch_col))

        if branch_col >= 0:
            lines.extend(self._render_branch_tree(branch_col))

        content = Text()
        for i, line in enumerate(lines):
            if i > 0:
                content.append("\n")
            content.append_text(line)

        border = "green" if self.converged else "blue"
        cycle_label = f"Cycle {self.cycle + 1} / {self.max_cycles}"

        return Panel(
            content,
            title="[bold]Attractor Pipeline[/bold]",
            subtitle=f"[dim]{cycle_label}[/dim]",
            border_style=border,
            padding=(1, 2),
        )
```

- [ ] **Step 4: Run full test suite**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/test_tui.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Verify import compatibility**

Run: `cd /home/vba2/git/StrebFlow && python -c "from attractor.tui import PipelineDisplay; print('OK')"`
Expected: `OK` — confirms `__main__.py` and `logging.py` imports still work.

- [ ] **Step 6: Commit**

```bash
git add src/attractor/tui.py tests/test_tui.py
git commit -m "feat(tui): assemble full DAG panel with branch tree and metadata

Wires up main row, metadata lines, and branch tree into a single
Rich Panel with dynamic border color and cycle subtitle."
```

---

### Task 6: Demo Script and Visual Verification

**Files:**
- Create: `demo_tui.py`

- [ ] **Step 1: Write the demo script**

```python
#!/usr/bin/env python3
"""Demo: animated pipeline TUI with simulated stages and a retry loop.

Run with: python demo_tui.py
No dependencies beyond Rich — no LLM or pipeline needed.
"""
import random
import time
import sys

# Allow running from project root without install
sys.path.insert(0, "src")

from attractor.tui import PipelineDisplay


def simulate_pipeline() -> None:
    display = PipelineDisplay(max_cycles=3)

    # Cycle 0: run through to a validation failure
    cycle_0_stages = [
        ("spec_loader", 0.5, 1.0),
        ("planner", 1.5, 2.5),
        ("implementer", 2.0, 4.0),
        ("test_runner", 1.0, 2.0),
        ("scenario_validator", 1.0, 1.5),
    ]

    # Cycle 1: retry succeeds
    cycle_1_stages = [
        ("implementer", 1.5, 3.0),
        ("test_runner", 0.8, 1.5),
        ("scenario_validator", 0.8, 1.2),
    ]

    finish_stages = [
        ("reviewer", 2.0, 3.0),
        ("done", 0.3, 0.5),
    ]

    with display:
        # ── Cycle 0 ──────────────────────────────────────────────
        for node, lo, hi in cycle_0_stages:
            display.on_node_enter(node)
            delay = random.uniform(lo, hi)

            if node == "implementer":
                n_calls = random.randint(3, 8)
                per_call = delay / n_calls
                for _ in range(n_calls):
                    time.sleep(per_call)
                    display.on_tool_call()
            else:
                time.sleep(delay)

            display.on_node_exit(node)

        # ── Diagnose (validator "failed" — diagnoser entered) ────
        display.on_node_enter("diagnoser")
        time.sleep(random.uniform(1.5, 2.5))
        display.on_node_exit("diagnoser")

        # ── Cycle 1 ──────────────────────────────────────────────
        display.on_cycle_start(1)

        for node, lo, hi in cycle_1_stages:
            display.on_node_enter(node)
            delay = random.uniform(lo, hi)

            if node == "implementer":
                n_calls = random.randint(2, 5)
                per_call = delay / n_calls
                for _ in range(n_calls):
                    time.sleep(per_call)
                    display.on_tool_call()
            else:
                time.sleep(delay)

            display.on_node_exit(node)

        # ── Convergence ──────────────────────────────────────────
        display.on_convergence()

        for node, lo, hi in finish_stages:
            display.on_node_enter(node)
            time.sleep(random.uniform(lo, hi))
            display.on_node_exit(node)

        # Hold final state
        time.sleep(2)

    print("\nDemo complete!")


if __name__ == "__main__":
    simulate_pipeline()
```

- [ ] **Step 2: Run the demo and visually verify**

Run: `cd /home/vba2/git/StrebFlow && python demo_tui.py`

Expected behavior:
1. Specs through Validate light up sequentially with spinners and elapsed times
2. Validate completes → diagnoser enters → validate turns red (✗), diagnose branch turns amber
3. Cycle resets to 2/3, implementer through validate re-run
4. Validate passes → border turns green, reviewer spins, then done
5. Final state holds for 2 seconds showing all-green main path

- [ ] **Step 3: Run full test suite to confirm nothing is broken**

Run: `cd /home/vba2/git/StrebFlow && python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add demo_tui.py
git commit -m "feat: add demo script for pipeline TUI visualization

Simulates all 8 stages with tool calls, a retry cycle through
diagnoser, and convergence. Run with: python demo_tui.py"
```
