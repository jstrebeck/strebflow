# Diff State Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `diff_history: list[str]` with `latest_diff: str` to eliminate redundant cumulative diffs sent to LLM pipeline phases.

**Architecture:** Single field rename across the state schema, with each consumer node updated to read the new field. Diagnoser gains truncation it was missing. Done node derives checkpoint count from `cycle` instead of list length.

**Tech Stack:** Python, LangGraph, pytest

---

### Task 1: Update state schema

**Files:**
- Modify: `src/attractor/state.py:26` (TypedDict field)
- Modify: `src/attractor/state.py:31` (truncate fields set)
- Test: `tests/test_state.py`

- [ ] **Step 1: Update test fixtures in `tests/test_state.py`**

In `test_save_and_load_run_state`, change the state fixture:

```python
# line 19: replace
"diff_history": [],
# with
"latest_diff": "",
```

In `test_save_run_state_excludes_large_fields`, change the state fixture:

```python
# line 43: replace
"diff_history": ["diff1", "diff2"],
# with
"latest_diff": "diff content",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py -v`
Expected: FAIL — `PipelineState` TypedDict still expects `diff_history`

- [ ] **Step 3: Update `PipelineState` in `src/attractor/state.py`**

Replace line 26:

```python
# before
diff_history: list[str]
# after
latest_diff: str
```

Add `"latest_diff"` to the truncate fields set on line 31:

```python
# before
_TRUNCATE_FIELDS = {"spec", "scenarios", "implementation_plan", "test_output", "steering_prompt"}
# after
_TRUNCATE_FIELDS = {"spec", "scenarios", "implementation_plan", "test_output", "steering_prompt", "latest_diff"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/state.py tests/test_state.py
git commit -m "refactor(state): replace diff_history list with latest_diff string"
```

---

### Task 2: Update initial state sites

**Files:**
- Modify: `src/attractor/__main__.py:60`
- Modify: `src/attractor/nodes/spec_loader.py:18`
- Test: `tests/test_nodes.py::test_spec_loader`

- [ ] **Step 1: Update spec_loader test fixture in `tests/test_nodes.py`**

In `test_spec_loader` (line 17), change:

```python
# before
"tool_call_history": [], "diff_history": [], "review_report": "",
# after
"tool_call_history": [], "latest_diff": "", "review_report": "",
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py::test_spec_loader -v`
Expected: FAIL — spec_loader returns `diff_history` key

- [ ] **Step 3: Update `spec_loader.py` line 18**

```python
# before
"diff_history": [],
# after
"latest_diff": "",
```

- [ ] **Step 4: Update `__main__.py` line 60**

```python
# before
"diff_history": [],
# after
"latest_diff": "",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_nodes.py::test_spec_loader -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/attractor/__main__.py src/attractor/nodes/spec_loader.py tests/test_nodes.py
git commit -m "refactor: update initial state to use latest_diff"
```

---

### Task 3: Update done node

**Files:**
- Modify: `src/attractor/nodes/done.py:15,22`
- Test: `tests/test_nodes.py::test_done_writes_summary`

- [ ] **Step 1: Update done test fixture in `tests/test_nodes.py`**

In `test_done_writes_summary` (line 66), change:

```python
# before
"diff_history": ["diff1", "diff2", "diff3"],
# after
"latest_diff": "diff3",
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py::test_done_writes_summary -v`
Expected: FAIL — `done` still reads `diff_history`

- [ ] **Step 3: Update `done.py`**

Remove line 15 (`diffs = ...`) and change line 22 from:

```python
# before (lines 15, 22)
diffs = state.get("diff_history", [])
...
f"**Files changed:** {len(diffs)} checkpoint(s)", "",
# after (line 22 only, diffs variable removed)
f"**Cycles used:** {cycles_used} / {max_cycles}",
```

The full updated summary_lines block becomes:

```python
summary_lines = [
    f"# Pipeline Run Summary", "",
    f"**Status:** {status}",
    f"**Cycles used:** {cycles_used} / {max_cycles}",
    f"**Satisfaction score:** {score}",
]
```

Note: the old "Files changed" line is removed entirely — cycles used is already reported on the line above it, and the checkpoint count was redundant with cycles.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_nodes.py::test_done_writes_summary -v`
Expected: PASS — the test asserts `"3" in result["summary"]` which still matches `cycles_used` (cycle=3)

- [ ] **Step 5: Commit**

```bash
git add src/attractor/nodes/done.py tests/test_nodes.py
git commit -m "refactor(done): use cycle count instead of diff_history length"
```

---

### Task 4: Update diagnoser node

**Files:**
- Modify: `src/attractor/nodes/diagnoser.py:30`
- Test: `tests/test_nodes.py::test_diagnoser_increments_cycle`

- [ ] **Step 1: Update diagnoser test fixture in `tests/test_nodes.py`**

In `test_diagnoser_increments_cycle` (line 128), change:

```python
# before
"diff_history": ["diff"], "review_report": "", "summary": ""}
# after
"latest_diff": "diff", "review_report": "", "summary": ""}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py::test_diagnoser_increments_cycle -v`
Expected: FAIL — diagnoser still reads `diff_history`

- [ ] **Step 3: Update `diagnoser.py`**

Add truncation helper and constant after the imports (before the function):

```python
_MAX_DIFF_CHARS = 200_000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n\n[... truncated ...]\n\n" + text[-half:]
```

Replace line 30 in the f-string:

```python
# before
{state.get('diff_history', [''])[-1] if state.get('diff_history') else 'No diff available'}"""
# after
{_truncate(state.get('latest_diff', ''), _MAX_DIFF_CHARS) or 'No diff available'}"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_nodes.py::test_diagnoser_increments_cycle -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/nodes/diagnoser.py tests/test_nodes.py
git commit -m "refactor(diagnoser): read latest_diff, add 200k truncation"
```

---

### Task 5: Update reviewer node

**Files:**
- Modify: `src/attractor/nodes/reviewer.py:25`
- Test: `tests/test_nodes.py::test_reviewer_returns_report`

- [ ] **Step 1: Update reviewer test fixture in `tests/test_nodes.py`**

In `test_reviewer_returns_report` (line 136), change:

```python
# before
"diff_history": ["diff content"], "review_report": "", "summary": ""}
# after
"latest_diff": "diff content", "review_report": "", "summary": ""}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py::test_reviewer_returns_report -v`
Expected: FAIL — reviewer still reads `diff_history`

- [ ] **Step 3: Update `reviewer.py` line 25**

```python
# before
all_diffs = "\n---\n".join(state.get("diff_history", []))
# after
latest_diff = state.get("latest_diff", "")
```

And update the f-string on line 33:

```python
# before
{_truncate(all_diffs, _MAX_DIFF_CHARS)}"""
# after
{_truncate(latest_diff, _MAX_DIFF_CHARS)}"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_nodes.py::test_reviewer_returns_report -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/nodes/reviewer.py tests/test_nodes.py
git commit -m "refactor(reviewer): read latest_diff instead of joining diff_history"
```

---

### Task 6: Update implementer node

**Files:**
- Modify: `src/attractor/nodes/implementer.py:164`
- Test: `tests/test_nodes.py::test_implementer_single_round_no_tools`

- [ ] **Step 1: Update implementer test fixture and assertion in `tests/test_nodes.py`**

In `test_implementer_single_round_no_tools` (line 190), change:

```python
# before
"diff_history": [], "review_report": "", "summary": "",
# after
"latest_diff": "", "review_report": "", "summary": "",
```

And update the assertion on line 194:

```python
# before
assert isinstance(result["diff_history"], list)
# after
assert isinstance(result["latest_diff"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_nodes.py::test_implementer_single_round_no_tools -v`
Expected: FAIL — implementer still returns `diff_history`

- [ ] **Step 3: Update `implementer.py` line 164**

```python
# before
"diff_history": state.get("diff_history", []) + ([diff] if diff else []),
# after
"latest_diff": diff or state.get("latest_diff", ""),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_nodes.py::test_implementer_single_round_no_tools -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/attractor/nodes/implementer.py tests/test_nodes.py
git commit -m "refactor(implementer): store latest_diff string instead of appending to list"
```

---

### Task 7: Update remaining test fixtures and full test run

**Files:**
- Modify: `tests/test_nodes.py` (lines 101, 120)

- [ ] **Step 1: Update planner test fixture**

In `test_planner_extracts_plan_and_test_command` (line 101), change:

```python
# before
"tool_call_history": [], "diff_history": [], "review_report": "", "summary": ""}
# after
"tool_call_history": [], "latest_diff": "", "review_report": "", "summary": ""}
```

- [ ] **Step 2: Update scenario_validator test fixture**

In `test_scenario_validator_returns_structured_result` (line 120), change:

```python
# before
"tool_call_history": [], "diff_history": ["some diff"], "review_report": "", "summary": ""}
# after
"tool_call_history": [], "latest_diff": "some diff", "review_report": "", "summary": ""}
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_nodes.py
git commit -m "test: update remaining fixtures to use latest_diff"
```
