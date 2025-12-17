"""Base scraper class for job platforms."""

from abc import ABC, abstractmethod
from typing import Optional

from ..client.mcp_client import BrightDataMCP
from ..models import JobPosting, ScraperResult


class BaseScraper(ABC):
    """Abstract base class for job scrapers."""

    # Subclasses must define these
    name: str = ""
    base_url: str = ""

    def __init__(self, mcp_client: Optional[BrightDataMCP] = None):
        """Initialize the scraper.

        Args:
            mcp_client: MCP client instance. Creates a new one if not provided.
        """
        self.mcp = mcp_client or BrightDataMCP()

    @abstractmethod
    async def search(
        self,
        query: str,
        location: str = "Beijing",
        page: int = 1,
    ) -> ScraperResult:
        """Search for jobs matching the query.

        Args:
            query: Search query (job title, keywords)
            location: Location filter
            page: Page number for pagination

        Returns:
            ScraperResult with list of jobs found
        """
        pass

    @abstractmethod
    async def get_detail(self, job_url: str) -> Optional[JobPosting]:
        """Get detailed information for a specific job.

        Args:
            job_url: URL of the job posting

        Returns:
            JobPosting with full details, or None if not found
        """
        pass

    @abstractmethod
    def parse_search_results(self, markdown: str) -> list[JobPosting]:
        """Parse search results page markdown into job listings.

        Args:
            markdown: Markdown content from search results page

        Returns:
            List of JobPosting objects (may have incomplete data)
        """
        pass

    @abstractmethod
    def parse_job_detail(self, markdown: str, job: JobPosting) -> JobPosting:
        """Parse job detail page markdown and update the job object.

        Args:
            markdown: Markdown content from job detail page
            job: Existing job object to update

        Returns:
            Updated JobPosting with full details
        """
        pass

    def build_search_url(
        self,
        query: str,
        location: str = "Beijing",
        page: int = 1,
    ) -> str:
        """Build the search URL for this platform.

        Args:
            query: Search query
            location: Location filter
            page: Page number

        Returns:
            Full search URL
        """
        # Subclasses should override this
        raise NotImplementedError

    async def scrape_url(self, url: str) -> str:
        """Scrape a URL and return markdown content.

        Args:
            url: URL to scrape

        Returns:
            Markdown content of the page
        """
        return await self.mcp.scrape_as_markdown(url)

    def generate_job_id(self, url: str) -> str:
        """Generate a unique job ID from the URL.

        Args:
            url: Job posting URL

        Returns:
            Unique identifier string
        """
        # Default implementation: use hash of URL
        import hashlib

        return hashlib.md5(url.encode()).hexdigest()[:12]
