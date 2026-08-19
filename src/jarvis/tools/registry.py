"""Construction of the deliberately small Phase 1 tool registry."""

from jarvis.core import Tool

from .clock import CurrentTimeTool


def phase_one_tools() -> tuple[Tool, ...]:
    """Return only the audited, side-effect-free Phase 1 tools."""
    return (CurrentTimeTool(),)
