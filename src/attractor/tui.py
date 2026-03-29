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
