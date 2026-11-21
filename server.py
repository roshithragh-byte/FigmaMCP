"""Root entrypoint shim for running or importing the Figma MCP server."""

from figma_mcp.server import create_app, create_server, main

__all__ = ["create_app", "create_server", "main"]

if __name__ == "__main__":
    main()
