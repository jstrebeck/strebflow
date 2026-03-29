# Diff State Optimization

## Problem

The pipeline stores cumulative diffs (diffed against the initial commit) in a `diff_history: list[str]` field. Because each entry is cumulative, later entries fully contain earlier ones. This causes:

1. **Reviewer** joins all entries with `"\n---\n".join(...)`, sending massively redundant content to the LLM.
2. **Diagnoser** sends the latest entry with zero truncation, risking token limit blowouts.
3. **State bloat** — `run_state.json` serializes the full list on every checkpoint.

## Design

Replace `diff_history: list[str]` with `latest_diff: str` across the pipeline.

### State schema (`state.py`)

- Remove `diff_history: list[str]` from `PipelineState`.
- Add `latest_diff: str`.
- Add `"latest_diff"` to `_TRUNCATE_FIELDS` so `run_state.json` stays small.

### Initial state (`__main__.py`, `spec_loader.py`)

- Change `"diff_history": []` to `"latest_diff": ""` in both initialization sites.

### Implementer (`implementer.py`)

- Change return from appending to a list:
  ```python
  # before
  "diff_history": state.get("diff_history", []) + ([diff] if diff else [])
  # after
  "latest_diff": diff or state.get("latest_diff", "")
  ```
- If no diff is produced this cycle, preserve the previous value.

### Diagnoser (`diagnoser.py`)

- Read `state.get("latest_diff", "")` instead of indexing into a list.
- Add a `_MAX_DIFF_CHARS = 200_000` limit and `_truncate()` helper (matching the pattern in validator and reviewer) to prevent unbounded prompt size.

### Reviewer (`reviewer.py`)

- Read `state.get("latest_diff", "")` instead of joining a list.
- Existing `_truncate(..., _MAX_DIFF_CHARS)` call stays as-is, just changes its input.

### Scenario Validator (`scenario_validator.py`)

- No change. It already calls `ws.get_diff()` directly from the workspace.

### Done (`done.py`)

- Replace `len(state.get("diff_history", []))` checkpoint count with `state.get("cycle", 0)`.
- Remove the `diffs` variable.

### Tests (`tests/test_nodes.py`, `tests/test_state.py`)

- Update all state fixtures: `"diff_history": [...]` becomes `"latest_diff": "..."`.
- Update assertion in implementer test: check `result["latest_diff"]` is a string, not a list.
- Update done/reviewer/diagnoser tests to use the new field name and shape.

### Documentation (`docs/` plan and spec files)

- Not updated. These are historical records of what was planned at the time they were written.

## Files changed

| File | Change |
|------|--------|
| `src/attractor/state.py` | Replace field in TypedDict, add to truncate set |
| `src/attractor/__main__.py` | Initial state key rename |
| `src/attractor/nodes/spec_loader.py` | Initial state key rename |
| `src/attractor/nodes/implementer.py` | Return `latest_diff` string instead of appending to list |
| `src/attractor/nodes/diagnoser.py` | Read new field, add truncation |
| `src/attractor/nodes/reviewer.py` | Read new field instead of joining list |
| `src/attractor/nodes/done.py` | Use `cycle` for count, drop `diffs` variable |
| `tests/test_nodes.py` | Update fixtures and assertions |
| `tests/test_state.py` | Update fixtures |

## Out of scope

- Changing `workspace.get_diff()` behavior (it still diffs against initial commit).
- Storing incremental diffs or any per-cycle history.
- Updating historical plan/spec docs in `docs/superpowers/`.
