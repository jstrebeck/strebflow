"""Structured logging setup using structlog."""
from __future__ import annotations
import sys
from pathlib import Path
from typing import TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from attractor.tui import PipelineDisplay


class _TUIWriter:
    """File-like object that routes writes through the TUI console."""
    def __init__(self, tui: PipelineDisplay) -> None:
        self._tui = tui
    def write(self, message: str) -> None:
        stripped = message.rstrip("\n")
        if stripped:
            self._tui.log(stripped)
    def flush(self) -> None:
        pass


def _make_tui_processor(tui: PipelineDisplay) -> structlog.types.Processor:
    """Structlog processor that dispatches events to the TUI display."""
    def processor(
        logger: structlog.types.WrappedLogger,
        method_name: str,
        event_dict: dict,
    ) -> dict:
        event_type = event_dict.get("event_type")
        if event_type:
            node = event_dict.get("node", "")
            if event_type == "NODE_ENTER":
                tui.on_node_enter(node)
            elif event_type == "NODE_EXIT":
                tui.on_node_exit(node, error=event_dict.get("error"))
            elif event_type == "CYCLE_START":
                tui.on_cycle_start(event_dict.get("cycle", 0))
            elif event_type == "TOOL_CALL_START":
                tui.on_tool_call(tool=event_dict.get("tool", ""), detail=event_dict.get("tool_detail", ""))
            elif event_type == "CONVERGENCE":
                tui.on_convergence()
        return event_dict
    return processor


def setup_logging(
    level: str = "INFO",
    structured: bool = True,
    log_file: Path | None = None,
    tui: PipelineDisplay | None = None,
) -> None:
    """Configure structlog for the pipeline."""
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if tui is not None:
        processors.append(_make_tui_processor(tui))
    if structured:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Write to TUI console (above live panel) or plain stdout, plus optional log file
    outputs: list = []
    if tui is not None:
        outputs.append(_TUIWriter(tui))
    else:
        outputs.append(sys.stdout)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        outputs.append(open(log_file, "a"))  # noqa: SIM115

    class MultiFileLoggerFactory:
        def __init__(self, files):
            self._files = files
        def __call__(self, *args, **kwargs):
            return MultiFileLogger(self._files)

    class MultiFileLogger:
        def __init__(self, files):
            self._files = files
            self.name = ""
        def msg(self, message: str) -> None:
            for f in self._files:
                f.write(message + "\n")
                f.flush()
        log = debug = info = warning = error = critical = fatal = msg

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=MultiFileLoggerFactory(outputs),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **initial_context: str) -> structlog.stdlib.BoundLogger:
    """Get a bound logger with initial context."""
    return structlog.get_logger(name, **initial_context)
