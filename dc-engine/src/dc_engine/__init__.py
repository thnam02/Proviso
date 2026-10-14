"""dc-engine: symbol-level context and edits for coding agents.

Phase 1 of the Delta Contracts layer: an index of the codebase (symbols,
signatures, imports, call graph), a slicer that hands agents compact
context instead of whole files, and an edit gate that edits by symbol and
reports only the diagnostics an edit introduced.
"""

__version__ = "0.1.0"

from .engine import Engine

__all__ = ["Engine", "__version__"]
