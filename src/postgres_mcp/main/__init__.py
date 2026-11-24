"""Composition-root package: re-exports the ``postgres-mcp`` entry point."""

from postgres_mcp.main.server import main

__all__ = ["main"]
