"""Error formatting at the MCP-to-A2A boundary."""


def describe_mcp_error(error: Exception) -> str:
    """Recover the tool error from nested MCP task groups."""
    if isinstance(error, ExceptionGroup):
        return "; ".join(describe_mcp_error(cause) for cause in error.exceptions)
    return str(error) or type(error).__name__
