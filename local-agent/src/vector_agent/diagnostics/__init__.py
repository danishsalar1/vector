"""VECTOR diagnostic framework.

Production diagnostic protocol, registry, and built-in diagnostics.
"""

from vector_agent.diagnostics.definition import Diagnostic, DiagnosticDefinition
from vector_agent.diagnostics.registry import DiagnosticRegistry, DuplicateDiagnosticError

__all__ = [
    "Diagnostic",
    "DiagnosticDefinition",
    "DiagnosticRegistry",
    "DuplicateDiagnosticError",
]
