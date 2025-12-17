"""Bright Data MCP client for web scraping."""

import asyncio
import logging
from typing import Optional, Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import TextContent

from ..config import get_settings

# Suppress noisy MCP validation warnings for custom Bright Data notifications
logging.getLogger("root").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    """Raised when MCP connection fails after retries."""
    pass


class MCPRateLimitError(Exception):
    """Raised when monthly rate limit is reached."""
    pass


class BrightDataMCP:
    """Client for interacting with Bright Data's MCP server."""

    def __init__(self, api_token: Optional[str] = None):
        """Initialize the MCP client.

        Args:
            api_token: Bright Data API token. If not provided, reads from settings.
        """
        settings = get_settings()
        self.api_token = api_token or settings.bright_data_api_token
        self.base_url = settings.bright_data_mcp_url
        self.monthly_limit = settings.monthly_request_limit

        if not self.api_token:
            raise ValueError(
                "Bright Data API token is required. "
                "Set BRIGHT_DATA_API_TOKEN environment variable or pass api_token parameter."
            )

    @property
    def url(self) -> str:
        """Get the full MCP URL with token."""
        return f"{self.base_url}?token={self.api_token}"

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> str:
        """Call an MCP tool and return the result with retry logic.

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Arguments to pass to the tool
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff

        Returns:
            The text content from the tool response

        Raises:
            MCPConnectionError: If connection fails after all retries
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                async with sse_client(self.url) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()

                        result = await session.call_tool(tool_name, arguments)

                        # Extract text content from result
                        if result.content and len(result.content) > 0:
                            content = result.content[0]
                            if isinstance(content, TextContent):
                                return content.text
                            # Handle other content types if needed
                            return str(content)

                        return ""

            except asyncio.TimeoutError as e:
                last_error = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"MCP timeout (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                continue

            except ConnectionError as e:
                last_error = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"MCP connection error (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                continue

            except Exception as e:
                # For other errors, check if it's retryable
                error_str = str(e).lower()
                if "timeout" in error_str or "connection" in error_str or "network" in error_str:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"MCP error (attempt {attempt + 1}/{max_retries + 1}): {e}, retrying in {delay:.1f}s...")
                        await asyncio.sleep(delay)
                    continue
                # Non-retryable error, raise immediately
                raise

        # All retries exhausted
        raise MCPConnectionError(
            f"Failed to connect to MCP server after {max_retries + 1} attempts. Last error: {last_error}"
        )

    async def scrape_as_markdown(self, url: str) -> str:
        """Scrape a URL and return the content as markdown.

        This is the primary method for scraping job pages.

        Args:
            url: The URL to scrape

        Returns:
            The page content as clean markdown
        """
        return await self._call_tool("scrape_as_markdown", {"url": url})

    async def search_engine(self, query: str, num_results: int = 10) -> str:
        """Perform a web search and return results.

        Args:
            query: Search query
            num_results: Number of results to return (default 10)

        Returns:
            Search results as text/markdown
        """
        return await self._call_tool(
            "search_engine",
            {"query": query, "num_results": num_results},
        )

    async def list_available_tools(self) -> list[str]:
        """List all available MCP tools.

        Returns:
            List of tool names available on the server
        """
        async with sse_client(self.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [tool.name for tool in tools.tools]

    async def test_connection(self) -> bool:
        """Test if the MCP connection is working.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            tools = await self.list_available_tools()
            return len(tools) > 0
        except Exception:
            return False


# Convenience function for one-off scraping
async def scrape_url(url: str, api_token: Optional[str] = None) -> str:
    """Scrape a URL using Bright Data MCP.

    Args:
        url: The URL to scrape
        api_token: Optional API token (uses settings if not provided)

    Returns:
        The page content as markdown
    """
    client = BrightDataMCP(api_token)
    return await client.scrape_as_markdown(url)
