"""Structured logging setup using structlog."""
from __future__ import annotations
import sys
from pathlib import Path
import structlog


def setup_logging(level: str = "INFO", structured: bool = True, log_file: Path | None = None) -> None:
    """Configure structlog for the pipeline."""
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if structured:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Write to both stdout and optionally a log file
    outputs = [sys.stdout]
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
