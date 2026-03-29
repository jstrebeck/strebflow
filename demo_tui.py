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
