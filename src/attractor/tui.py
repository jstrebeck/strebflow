"""Terminal UI for the attractor pipeline — animated DAG topology display."""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
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

_ICON_MAP = {
    StageStatus.PENDING: ("·", "dim"),
    StageStatus.ACTIVE: ("▸", "bold cyan"),
    StageStatus.COMPLETED: ("✓", "green"),
    StageStatus.FAILED: ("✗", "red"),
}

_LABEL_STYLES = {
    StageStatus.PENDING: "dim",
    StageStatus.ACTIVE: "bold cyan",
    StageStatus.COMPLETED: "green",
    StageStatus.FAILED: "red",
}


_ACTIVITY_LOG_LINES = 6
_SYSTEM_LOG_LINES = 4


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

        self._activity_log: deque[Text] = deque(maxlen=_ACTIVITY_LOG_LINES)
        self._system_log: deque[Text] = deque(maxlen=_SYSTEM_LOG_LINES)

        # Pre-compute fixed panel height to prevent flickering.
        # Content: 1 main row + 2 metadata + branch tree lines.
        # Panel chrome: 2 border lines + 2 padding lines.
        branch_lines = 0
        for targets in self.topology.branch_points.values():
            branch_lines += 1  # spacer above branches
            for i, target in enumerate(targets):
                branch_lines += 1  # branch line
                if target.back_edge_to:
                    branch_lines += 1  # back-edge line
                if i < len(targets) - 1:
                    branch_lines += 1  # spacer between branches
        # system log + main + meta + branches + activity header + activity lines + chrome
        self._panel_height = (
            1 + _SYSTEM_LOG_LINES  # system log header + lines
            + 1 + 2 + branch_lines  # main row + metadata + branches
            + 1 + _ACTIVITY_LOG_LINES  # activity header + lines
            + 4  # panel chrome (border + padding)
        )

    # ── Rich renderable protocol ────────────────────────────────────

    def __rich_console__(
        self, console: Console, options: ConsoleOptions,
    ) -> RenderResult:
        yield self._render()

    # ── Context manager ──────────────────────────────────────────────

    def start(self) -> None:
        self._live = Live(
            self,
            console=self.console,
            auto_refresh=False,
        )
        self._live.start()
        self._start_timer()

    def stop(self) -> None:
        self._stop_timer()
        if self._live:
            self._live.stop()
            self._live = None

    def __enter__(self) -> PipelineDisplay:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # ── Refresh control ─────────────────────────────────────────────

    def _refresh(self) -> None:
        if self._live:
            self._live.refresh()

    def _start_timer(self) -> None:
        """Kick off a 1-second repeating timer to update the elapsed display."""
        import threading
        self._timer_stop = threading.Event()

        def _tick() -> None:
            while not self._timer_stop.wait(1.0):
                self._refresh()

        self._timer_thread = threading.Thread(target=_tick, daemon=True)
        self._timer_thread.start()

    def _stop_timer(self) -> None:
        if hasattr(self, "_timer_stop"):
            self._timer_stop.set()

    # ── Event handlers ───────────────────────────────────────────────

    def on_node_enter(self, node: str) -> None:
        if node in self.stages:
            stage = self.stages[node]
            stage.status = StageStatus.ACTIVE
            stage.start_time = time.monotonic()
            stage.end_time = None
            if node == "implementer":
                stage.metadata["tool_calls"] = 0
            entry = Text()
            entry.append("  ▸ ", style="cyan")
            entry.append(stage.label, style="bold cyan")
            entry.append(" started", style="dim")
            self._activity_log.append(entry)
        if node in self._branch_failure_map and not self.converged:
            bp = self._branch_failure_map[node]
            if bp in self.stages:
                self.stages[bp].status = StageStatus.FAILED
        self._refresh()

    def on_node_exit(self, node: str, error: str | None = None) -> None:
        if node in self.stages:
            stage = self.stages[node]
            stage.status = StageStatus.FAILED if error else StageStatus.COMPLETED
            stage.end_time = time.monotonic()
            entry = Text()
            if error:
                entry.append("  ✗ ", style="red")
                entry.append(stage.label, style="red")
                entry.append(" failed", style="dim red")
            else:
                entry.append("  ✓ ", style="green")
                entry.append(stage.label, style="green")
                elapsed = format_elapsed(stage.elapsed)
                entry.append(f" done ({elapsed})", style="dim")
            self._activity_log.append(entry)
        self._refresh()

    def on_cycle_start(self, cycle: int) -> None:
        self.cycle = cycle
        if cycle > 0:
            for name in self.topology.cycle_resettable:
                if name in self.stages:
                    stage = self.stages[name]
                    if stage.status == StageStatus.ACTIVE:
                        continue
                    stage.status = StageStatus.PENDING
                    stage.start_time = None
                    stage.end_time = None
                    stage.metadata.clear()
        self._refresh()

    def on_tool_call(self, tool: str = "", detail: str = "") -> None:
        for stage in self.stages.values():
            if stage.status == StageStatus.ACTIVE and stage.name == "implementer":
                stage.metadata["tool_calls"] = stage.metadata.get("tool_calls", 0) + 1
        if tool:
            entry = Text()
            entry.append("    ", style="dim")
            entry.append(tool, style="dim cyan")
            if detail:
                entry.append(f" {detail}", style="dim")
            self._activity_log.append(entry)
        self._refresh()

    def on_convergence(self) -> None:
        self.converged = True
        entry = Text()
        entry.append("  ✓ ", style="bold green")
        entry.append("scenarios passed", style="green")
        self._activity_log.append(entry)
        self._refresh()

    # ── Log output ───────────────────────────────────────────────────

    def log(self, message: str) -> None:
        # Skip event_type messages — those are already shown in Activity
        try:
            data = json.loads(message)
            if data.get("event_type"):
                return
        except (json.JSONDecodeError, TypeError):
            pass
        entry = self._format_log_entry(message)
        self._system_log.append(entry)
        if self._live:
            self._refresh()
        else:
            print(entry.plain)

    @staticmethod
    def _format_log_entry(message: str) -> Text:
        """Parse a structured log message into a styled Text line."""
        entry = Text()
        try:
            data = json.loads(message)
            ts = data.get("timestamp", "")
            # Extract HH:MM:SS from ISO timestamp
            if "T" in ts:
                ts = ts.split("T")[1][:8]
            event = data.get("event", message)
            entry.append(f"  {ts}", style="dim")
            entry.append(f"  {event}", style="dim white")
            # Append first interesting key=value pair
            skip = {"event", "timestamp", "level", "log_level", "logger", "logger_name", "event_type"}
            for k, v in data.items():
                if k not in skip and v:
                    entry.append(f"  {k}=", style="dim")
                    entry.append(str(v), style="dim cyan")
                    break
        except (json.JSONDecodeError, TypeError):
            entry.append(f"  {message}", style="dim")
        return entry

    # ── Rendering ────────────────────────────────────────────────────

    @staticmethod
    def _stage_icon(stage: StageInfo) -> tuple[str, str]:
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

    def _make_metadata_spacer(self, branch_col: int) -> Text:
        """Empty line that preserves the branch │ connector."""
        spacer = Text()
        if branch_col > 0:
            spacer.append(" " * branch_col)
            spacer.append("│", style="dim")
        return spacer

    def _render_metadata_lines(self, branch_col: int) -> list[Text]:
        """Render elapsed time and tool calls below the active main-path stage.

        Always returns exactly 2 lines to keep panel height stable.
        """
        positions = self._compute_stage_positions()

        active: StageInfo | None = None
        for node_name in self.topology.main_path:
            stage = self.stages[node_name]
            if stage.status == StageStatus.ACTIVE:
                active = stage
                break

        if active is None:
            return [self._make_metadata_spacer(branch_col)] * 2

        col = positions.get(active.name, 0)
        elapsed_str = format_elapsed(active.elapsed)

        line = Text()
        line.append(" " * col)
        line.append(f"   {elapsed_str}", style="cyan")
        if branch_col > 0 and len(line.plain) < branch_col:
            line.append(" " * (branch_col - len(line.plain)))
            line.append("│", style="dim")

        tool_calls = active.metadata.get("tool_calls", 0)
        if active.name == "implementer" and tool_calls > 0:
            tc_line = Text()
            tc_line.append(" " * col)
            tc_line.append(f"   {tool_calls} tool calls", style="dim cyan")
            if branch_col > 0 and len(tc_line.plain) < branch_col:
                tc_line.append(" " * (branch_col - len(tc_line.plain)))
                tc_line.append("│", style="dim")
            return [line, tc_line]

        return [line, self._make_metadata_spacer(branch_col)]

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

    def _render_system_log(self) -> list[Text]:
        """Render the system log section above the DAG."""
        lines: list[Text] = []
        header = Text()
        header.append("  ─── Log ", style="dim")
        header.append("─" * 45, style="dim")
        lines.append(header)

        for entry in self._system_log:
            lines.append(entry)
        for _ in range(_SYSTEM_LOG_LINES - len(self._system_log)):
            lines.append(Text())

        return lines

    def _render_activity_log(self) -> list[Text]:
        """Render the rolling activity log section."""
        lines: list[Text] = []
        header = Text()
        header.append("  ─── Activity ", style="dim")
        header.append("─" * 40, style="dim")
        lines.append(header)

        for entry in self._activity_log:
            lines.append(entry)
        for _ in range(_ACTIVITY_LOG_LINES - len(self._activity_log)):
            lines.append(Text())

        return lines

    def _render(self) -> Panel:
        """Assemble the full DAG display panel."""
        lines: list[Text] = []

        lines.extend(self._render_system_log())

        main_row, branch_col = self._render_main_row()
        lines.append(main_row)

        lines.extend(self._render_metadata_lines(branch_col))

        if branch_col >= 0:
            lines.extend(self._render_branch_tree(branch_col))

        lines.extend(self._render_activity_log())

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
            expand=True,
            height=self._panel_height,
        )
