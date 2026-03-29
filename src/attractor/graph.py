"""LangGraph StateGraph definition for the attractor pipeline."""
from __future__ import annotations
import functools
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END

from attractor.config import PipelineConfig
from attractor.llm_client import LLMClient
from attractor.state import PipelineState, save_run_state
from attractor.logging import get_logger

from attractor.nodes.spec_loader import spec_loader
from attractor.nodes.planner import planner
from attractor.nodes.implementer import implementer
from attractor.nodes.test_runner import test_runner
from attractor.nodes.scenario_validator import scenario_validator
from attractor.nodes.diagnoser import diagnoser
from attractor.nodes.reviewer import reviewer
from attractor.nodes.done import done


def route_after_validation(state: dict[str, Any]) -> str:
    logger = get_logger("attractor.graph")
    validation = state.get("validation_result", {})
    passed = validation.get("passed", False)
    cycle = state.get("cycle", 0)
    max_cycles = state.get("max_cycles", 10)
    if passed:
        logger.info("scenarios passed", event_type="CONVERGENCE", cycle=cycle)
        return "reviewer"
    if cycle >= max_cycles:
        return "done"
    return "diagnoser"


def _wrap_node(node_fn, name: str, config: PipelineConfig | None = None, llm: LLMClient | None = None):
    @functools.wraps(node_fn)
    async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
        logger = get_logger("attractor.graph", node=name)
        logger.info("entering node", event_type="NODE_ENTER")

        try:
            model_map = {
                "planner": config.llm.models.planner if config else None,
                "implementer": config.llm.models.implementer if config else None,
                "scenario_validator": config.llm.models.validator if config else None,
                "diagnoser": config.llm.models.diagnoser if config else None,
                "reviewer": config.llm.models.reviewer if config else None,
            }
            if name == "test_runner" and config:
                result = await node_fn(
                    state,
                    config_test_command=config.pipeline.test_command,
                    test_timeout=config.pipeline.test_timeout,
                )
            elif name == "implementer" and llm and config:
                result = await node_fn(
                    state, llm=llm, model=model_map[name],
                    context_char_limit=config.pipeline.context_char_limit,
                    tool_output_truncation=config.pipeline.tool_output_truncation,
                    loop_detection_window=config.pipeline.loop_detection_window,
                )
            elif name in model_map and model_map[name] and llm:
                result = await node_fn(state, llm=llm, model=model_map[name])
            else:
                result = await node_fn(state)
        except Exception as e:
            ws_path = state.get("workspace_path", "")
            if ws_path:
                save_run_state(
                    state,
                    Path(ws_path) / "run_state.json",
                    status="error",
                    node=name,
                    error=str(e),
                )
            logger.error("node failed", event_type="NODE_EXIT", error=str(e))
            raise

        merged = {**state, **result}
        ws_path = merged.get("workspace_path", "")
        if ws_path:
            save_run_state(
                merged,
                Path(ws_path) / "run_state.json",
                status="running",
                node=name,
            )

        logger.info("exiting node", event_type="NODE_EXIT")
        return result

    return wrapper


def build_graph(config: PipelineConfig, llm: LLMClient) -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("spec_loader", _wrap_node(spec_loader, "spec_loader", config, llm))
    graph.add_node("planner", _wrap_node(planner, "planner", config, llm))
    graph.add_node("implementer", _wrap_node(implementer, "implementer", config, llm))
    graph.add_node("test_runner", _wrap_node(test_runner, "test_runner", config, llm))
    graph.add_node("scenario_validator", _wrap_node(scenario_validator, "scenario_validator", config, llm))
    graph.add_node("diagnoser", _wrap_node(diagnoser, "diagnoser", config, llm))
    graph.add_node("reviewer", _wrap_node(reviewer, "reviewer", config, llm))
    graph.add_node("done", _wrap_node(done, "done", config, llm))

    graph.set_entry_point("spec_loader")

    graph.add_edge("spec_loader", "planner")
    graph.add_edge("planner", "implementer")
    graph.add_edge("implementer", "test_runner")
    graph.add_edge("test_runner", "scenario_validator")

    graph.add_conditional_edges(
        "scenario_validator",
        route_after_validation,
        {"reviewer": "reviewer", "diagnoser": "diagnoser", "done": "done"},
    )

    graph.add_edge("diagnoser", "implementer")
    graph.add_edge("reviewer", "done")
    graph.add_edge("done", END)

    return graph.compile()
