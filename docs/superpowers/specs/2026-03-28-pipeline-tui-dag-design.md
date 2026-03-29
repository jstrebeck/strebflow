# Pipeline TUI — DAG Topology Visualization

**Date:** 2026-03-28
**Status:** Approved
**Replaces:** Current `PipelineDisplay` in `src/attractor/tui.py`

## Summary

Replace the existing text-checklist pipeline display with an animated DAG (directed acyclic graph) visualization rendered in Unicode box-drawing characters. The new display shows the true pipeline topology — including the three-way branch from `validate` and the `diagnoser → implementer` retry loop — with per-stage status coloring, animated spinners, and live elapsed timers. Pure terminal, works over SSH.

## Goals

- Visually impressive terminal UI that conveys the pipeline "flow"
- Show the actual topology including branches and retry loops
- Clear at-a-glance status for each stage
- Live elapsed time and tool call counts
- Drop-in replacement — zero changes to callers
- Configurable stages and topology for future pipelines

## Non-Goals

- Web-based dashboard (terminal-only)
- Pixel-perfect circular arrow aesthetics (box-drawing art instead)
- Dynamic graph layout computation (topology is static/predefined)

## Architecture

### Module Structure

Single file replacement: `src/attractor/tui.py`. No new modules, no new dependencies.

Contains:
- `StageStatus` — Enum: `PENDING`, `ACTIVE`, `COMPLETED`, `FAILED`
- `StageInfo` — Dataclass: name, display_label, status, start_time, end_time, metadata dict
- `PipelineTopology` — Dataclass: defines the DAG as stages + edges + branch points
- `PipelineDisplay` — Main class: rendering engine, event handlers, Rich Live display

### Files Changed

| File | Change |
|------|--------|
| `src/attractor/tui.py` | Full rewrite |
| `demo_tui.py` (new) | Standalone demo script in project root |

### Files NOT Changed

- `src/attractor/logging.py` — existing structlog event dispatch stays as-is
- `src/attractor/graph.py` — no changes
- `src/attractor/__main__.py` — no changes
- No other files affected

## Layout Engine

### Topology Definition

The DAG is described as data, not a rendering template:

- **Main path:** `specs → plan → implement → test → validate → review → done`
- **Branch point** at `validate` with three outgoing edges:
  - `validate → reviewer` (scenarios passed)
  - `validate → diagnoser` (scenarios failed, retries remain)
  - `validate → done` (scenarios failed, cycles exhausted)
- **Back-edge:** `diagnoser → implementer` (retry loop)

Stored as a `PipelineTopology` dataclass with an edge list and branch point metadata.

### Character Grid Rendering

Each render frame (12fps via Rich `Live`):

1. **Main row** — built left-to-right: `[status_icon] Label ──→` for each main-path stage
2. **Branch tree** — below the branch point, drawn with box-drawing characters:
   ```
   ──┬──→ Review ──→ Done
     │
     ├──→ Diagnose
     │       ╰──→ Implement
     │
     ╰──→ Done (exhausted)
   ```
3. **Stage metadata** — elapsed time and tool calls rendered below the active stage
4. **Panel wrapper** — Rich `Panel` with dynamic border color and "Cycle N / M" subtitle

### Width Handling

- **Full layout:** requires ~110 chars (comfortable at 120)
- **Narrow fallback:** if terminal < 100 chars, main path wraps after `test` with a `↓` connector, creating a two-line flow
- **Minimum viable width:** ~80 chars

### Rendering Technology

Rich `Text` objects assembled line-by-line. Not `Table` or `Columns` — this gives character-level control over alignment and coloring without fighting Rich's layout abstractions.

## State Management

### Per-Stage Tracking

Each stage has a `StageInfo` instance:
- `status: StageStatus` — one of PENDING, ACTIVE, COMPLETED, FAILED
- `start_time: float | None` — `time.monotonic()` when stage entered
- `end_time: float | None` — when stage exited
- `metadata: dict` — arbitrary per-stage data (e.g. `{"tool_calls": 5}`)

Elapsed time for the active stage is computed live each render frame: `now - start_time`.

### Event Handlers (unchanged API)

| Method | Trigger | Action |
|--------|---------|--------|
| `on_node_enter(node)` | NODE_ENTER event | Set stage ACTIVE, record start_time |
| `on_node_exit(node, error)` | NODE_EXIT event | Set COMPLETED or FAILED, record end_time |
| `on_cycle_start(cycle)` | CYCLE_START event | Reset cycle-resettable stages to PENDING |
| `on_tool_call()` | TOOL_CALL_START event | Increment tool_calls in active stage metadata |
| `on_convergence()` | CONVERGENCE event | Set converged flag, border → green |

### Cycle Resets

When `on_cycle_start(cycle)` fires, stages in the cycle-resettable set (`implementer`, `test_runner`, `scenario_validator`, `diagnoser`) reset to PENDING. This makes the main row show fresh status for the new retry attempt.

### Branch State Visualization

The branch tree below validate reflects actual execution:

| Condition | Visual |
|-----------|--------|
| Validate hasn't run | All three branches dim/pending |
| Validate passes | `reviewer` branch lights up cyan (active) |
| Validate fails, retries remain | `diagnoser` branch lights up amber/yellow |
| Validate fails, exhausted | `done (exhausted)` branch lights up |

## Visual Design

### Color Scheme

| Stage Status | Icon | Label Style | Border/Arrow |
|-------------|------|-------------|-------------|
| Pending | `·` | Dim gray | Dim gray |
| Active | `⠋` (spinner) | Bold cyan | Cyan |
| Completed | `✓` | Green | Green |
| Failed | `✗` | Red | Red |

### Special Colors

- **Retry/diagnose path active:** Amber/yellow for the branch lines
- **Border:** Blue during execution, green on convergence
- **Panel subtitle:** "Cycle N / M" in dim text

### Active Stage Detail

Below the active stage on the main row:
- Elapsed time: `12.4s` or `1m 23.4s` (ticks live)
- Tool call count (implementer only): `3 tool calls`

## Integration API

### Constructor

```python
PipelineDisplay(
    max_cycles: int = 3,
    topology: PipelineTopology | None = None,  # None = default attractor topology
)
```

### Context Manager

```python
with PipelineDisplay(max_cycles=3) as tui:
    # pipeline execution...
```

Starts Rich `Live` on enter, stops on exit. Same as today.

### Custom Topology

```python
topology = PipelineTopology(
    stages=[
        ("fetch", "Fetch"),        # (internal_name, display_label)
        ("transform", "Transform"),
        ("load", "Load"),
        ("verify", "Verify"),
    ],
    edges=[("fetch", "transform"), ("transform", "load"), ("load", "verify")],
    branch_points={},  # no branches
    cycle_resettable=set(),  # no retry loop
)
tui = PipelineDisplay(max_cycles=1, topology=topology)
```

The default attractor topology maps internal node names to short display labels:
`spec_loader→Specs`, `planner→Plan`, `implementer→Implement`, `test_runner→Test`,
`scenario_validator→Validate`, `diagnoser→Diagnose`, `reviewer→Review`, `done→Done`.

## Demo Script

`demo_tui.py` in project root:
- Simulates all 8 stages with randomized delays (0.5s–3s per stage)
- Runs 1 retry cycle: validate fails → diagnoser → implementer → test → validate passes → reviewer → done
- Runnable standalone: `python demo_tui.py`
- No dependencies beyond Rich (no LLM, no pipeline)

## Testing

- The existing `PipelineDisplay` has no unit tests — the new one won't add mandatory tests either
- The demo script serves as the primary visual verification tool
- Integration testing: run the actual pipeline and observe the TUI
