"""
Utility functions for sk_agents.

This module provides various utility functions including PDF text extraction.
"""

import importlib.util
from pathlib import Path

from sk_agents.utils.pdf_extractor import PDFExtractionError, PDFExtractor

# Re-export functions from the parent-level utils.py module
# When the utils/ package was created, we need to maintain backward compatibility
# by re-exporting these functions that were originally in sk_agents/utils.py

# Load utils.py as a separate module to avoid circular import
_utils_py_path = Path(__file__).parent.parent / "utils.py"
_spec = importlib.util.spec_from_file_location("sk_agents._utils_py", _utils_py_path)
if _spec and _spec.loader:
    _utils_py = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_utils_py)

    docstring_parameter = _utils_py.docstring_parameter
    get_sse_event_for_response = _utils_py.get_sse_event_for_response
    initialize_plugin_loader = _utils_py.initialize_plugin_loader
else:
    raise ImportError("Failed to load sk_agents/utils.py")

__all__ = [
    "PDFExtractor",
    "PDFExtractionError",
    "docstring_parameter",
    "get_sse_event_for_response",
    "initialize_plugin_loader",
]
