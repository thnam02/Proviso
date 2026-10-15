"""dc-engine: symbol-level context, edits, and delta contracts for agents.

An index of the codebase (symbols, signatures, imports, call graph), a
slicer that hands agents compact context instead of whole files, an edit
gate that edits by symbol, and delta contracts that freeze a baseline
then diff old vs new behaviour with probes.
"""

__version__ = "0.1.0"

from .engine import Engine

__all__ = ["Engine", "__version__"]
