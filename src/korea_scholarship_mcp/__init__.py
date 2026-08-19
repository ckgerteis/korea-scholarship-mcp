"""korea-scholarship-mcp — MCP server for KCI and OAK.

Importing this package does not start the server; call `main()`, run
`python -m korea_scholarship_mcp`, or use the installed
`korea-scholarship-mcp` console script.
"""
from .server import __version__, main

__all__ = ["main", "__version__"]
