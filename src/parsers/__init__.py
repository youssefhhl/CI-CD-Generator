"""Language-specific parsers.

Each parser turns repository information into a normalized
:class:`~src.domain.ProjectProfile`. Supported: Maven-based Java, Python
(requirements.txt / pyproject.toml), and Node.js (package.json).
"""

from .java_parser import JavaParser
from .node_parser import NodeParser
from .python_parser import PythonParser

__all__ = ["JavaParser", "PythonParser", "NodeParser"]
