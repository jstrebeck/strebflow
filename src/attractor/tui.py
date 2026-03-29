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

    # ── Rendering (stub — filled in Task 3-5) ────────────────────────

    def _refresh(self) -> None:
        if self._live:
            self._live.update(self._render())

    def _render(self) -> Panel:
        return Panel("(rendering not yet implemented)", border_style="blue")
