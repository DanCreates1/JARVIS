"""Construction of the deliberately small Phase 1 tool registry."""

from collections.abc import Iterable
from pathlib import Path

from jarvis.core import Tool

from .clock import CurrentTimeTool
from .files import ReadTextFileTool
from .system_status import SystemStatusTool


def phase_one_tools(*, allowed_file_roots: Iterable[Path]) -> tuple[Tool, ...]:
    """Return only audited, bounded, side-effect-free Phase 1 tools."""
    roots = tuple(allowed_file_roots)
    return (
        CurrentTimeTool(),
        SystemStatusTool(probe_path=roots[0]),
        ReadTextFileTool(roots),
    )
