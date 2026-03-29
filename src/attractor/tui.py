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
