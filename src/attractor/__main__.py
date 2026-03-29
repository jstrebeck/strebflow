"""CLI entrypoint for the attractor pipeline."""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from attractor.config import load_config
from attractor.llm_client import LLMClient
from attractor.logging import setup_logging, get_logger
from attractor.graph import build_graph
from attractor.tui import PipelineDisplay
from attractor.workspace import Workspace


def generate_run_id() -> str:
    return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


async def cmd_run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    setup_logging(level=config.logging.level, structured=config.logging.structured)
    logger = get_logger("attractor.cli")

    run_id = args.run_id or generate_run_id()
    logger.info("starting pipeline run", run_id=run_id)

    workspace = Workspace(
        base_path=config.workspace.base_path,
        run_id=run_id,
        target_repo=args.repo,
    )

    tui = PipelineDisplay(max_cycles=config.pipeline.max_cycles)

    log_path = Path(workspace.path) / "run.log"
    setup_logging(level=config.logging.level, structured=config.logging.structured, log_file=log_path, tui=tui)
    logger = get_logger("attractor.cli")
    logger.info("workspace created", path=workspace.path)

    llm = LLMClient(providers=config.llm.providers)

    try:
        graph = build_graph(config, llm)
        initial_state = {
            "spec": str(Path(args.spec).resolve()),
            "scenarios": str(Path(args.scenarios).resolve()),
            "workspace_path": workspace.path,
            "implementation_plan": "",
            "cycle": 0,
            "max_cycles": config.pipeline.max_cycles,
            "steering_prompt": "",
            "test_output": "",
            "test_exit_code": -1,
            "test_command": config.pipeline.test_command or "",
            "validation_result": {},
            "tool_call_history": [],
            "latest_diff": "",
            "review_report": "",
            "summary": "",
        }
        with tui:
            result = await graph.ainvoke(initial_state)
        logger.info("pipeline complete", run_id=run_id, status="done")
        print(f"\nRun complete: {run_id}")
        print(f"Workspace: {workspace.path}")
        if result.get("summary"):
            print(f"\n{result['summary']}")
    finally:
        await llm.close()


def cmd_resume(args: argparse.Namespace) -> None:
    raise NotImplementedError(
        "Resume is not yet implemented. See design spec for planned approach."
    )


def cmd_status(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    run_dir = Path(config.workspace.base_path) / args.run_id
    state_file = run_dir / "run_state.json"

    if not state_file.exists():
        print(f"No run state found for '{args.run_id}'")
        print(f"Looked in: {state_file}")
        sys.exit(1)

    state = json.loads(state_file.read_text())
    print(f"Run: {args.run_id}")
    print(f"Status: {state.get('status', 'unknown')}")
    print(f"Cycle: {state.get('cycle', '?')} / {state.get('max_cycles', '?')}")
    if state.get("current_node"):
        print(f"Current node: {state['current_node']}")
    if state.get("validation_result"):
        vr = state["validation_result"]
        print(f"Passed: {vr.get('passed', '?')}")
        print(f"Score: {vr.get('satisfaction_score', '?')}")
    if state.get("error"):
        print(f"Error: {state['error']}")

    summary_file = run_dir / "summary.md"
    if summary_file.exists():
        print(f"\n--- Summary ---\n{summary_file.read_text()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="attractor", description="LangGraph-based agentic coding pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute a pipeline run")
    run_parser.add_argument("--spec", required=True, help="Path to spec markdown file")
    run_parser.add_argument("--scenarios", required=True, help="Path to scenarios markdown file")
    run_parser.add_argument("--repo", required=True, help="Path to target repository")
    run_parser.add_argument("--run-id", default=None, help="Run ID (auto-generated if omitted)")
    run_parser.add_argument("--config", default="pipeline_config.yaml", help="Config file path")

    resume_parser = subparsers.add_parser("resume", help="Resume a failed run")
    resume_parser.add_argument("--run-id", required=True, help="Run ID to resume")
    resume_parser.add_argument("--config", default="pipeline_config.yaml", help="Config file path")

    status_parser = subparsers.add_parser("status", help="Show run status")
    status_parser.add_argument("--run-id", required=True, help="Run ID to check")
    status_parser.add_argument("--config", default="pipeline_config.yaml", help="Config file path")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
