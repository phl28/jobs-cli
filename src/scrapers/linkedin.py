"""LinkedIn job scraper."""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin, unquote

from . import register_scraper
from .base import BaseScraper
from ..models import JobPosting, ScraperResult
from ..utils.parser import extract_tags


# LinkedIn location IDs (geoId)
LOCATION_IDS = {
    "beijing": "102255891",
    "北京": "102255891",
    "shanghai": "102772228",
    "上海": "102772228",
    "china": "102890883",
    "中国": "102890883",
    "shenzhen": "102214077",
    "深圳": "102214077",
    "guangzhou": "102511908",
    "广州": "102511908",
}


@register_scraper("linkedin")
class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn Jobs."""

    name = "linkedin"
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

    def build_search_url(
        self,
        query: str,
        location: str = "China",
        page: int = 1,
    ) -> str:
        """Build the LinkedIn guest jobs API URL.

        Args:
            query: Search query
            location: Location name
            page: Page number (25 jobs per page)

        Returns:
            Full search URL
        """
        # Calculate start offset (25 jobs per page)
        start = (page - 1) * 25
        
        # Always search China-wide for better results, then filter by location
        # The city-specific geoIds don't work well with the guest API
        geo_id = LOCATION_IDS.get("china")
        
        # Build URL - always use "China" in the URL for best results
        params = f"?keywords={quote(query)}&location=China&geoId={geo_id}&start={start}"
        return f"{self.base_url}{params}"

    async def search(
        self,
        query: str,
        location: str = "China",
        page: int = 1,
        filter_location: bool = True,
    ) -> ScraperResult:
        """Search for jobs on LinkedIn.

        Args:
            query: Search query
            location: Location filter
            page: Page number
            filter_location: Whether to filter results by location

        Returns:
            ScraperResult with jobs found
        """
        url = self.build_search_url(query, location, page)

        try:
            markdown = await self.scrape_url(url)
            jobs = self.parse_search_results(markdown)

            # Filter jobs by location if requested
            if filter_location and location.lower() not in ["china", "中国"]:
                jobs = self._filter_by_location(jobs, location)

            # LinkedIn guest API returns up to 25 jobs per page
            has_more = len(jobs) >= 10  # Lower threshold since we filter

            return ScraperResult(
                jobs=jobs,
                total_count=len(jobs),
                page=page,
                has_more=has_more,
                source=self.name,
            )
        except Exception as e:
            return ScraperResult(
                jobs=[],
                total_count=0,
                page=page,
                has_more=False,
                source=self.name,
                error=str(e),
            )

    async def get_detail(self, job_url: str) -> Optional[JobPosting]:
        """Get detailed job information."""
        # LinkedIn detail pages require auth, skip for now
        return None

    def parse_job_detail(self, markdown: str, job: JobPosting) -> JobPosting:
        """Parse job detail page (not implemented for LinkedIn).
        
        Args:
            markdown: Detail page markdown
            job: Existing job object
            
        Returns:
            Unchanged job object
        """
        return job

    def _filter_by_location(self, jobs: list[JobPosting], location: str) -> list[JobPosting]:
        """Filter jobs by location.

        Args:
            jobs: List of jobs to filter
            location: Target location (e.g., "Beijing", "Shanghai")

        Returns:
            Filtered list of jobs matching the location
        """
        location_lower = location.lower()
        
        # Map common location names to patterns
        location_patterns = {
            "beijing": ["beijing", "北京"],
            "北京": ["beijing", "北京"],
            "shanghai": ["shanghai", "上海"],
            "上海": ["shanghai", "上海"],
            "shenzhen": ["shenzhen", "深圳"],
            "深圳": ["shenzhen", "深圳"],
            "guangzhou": ["guangzhou", "广州"],
            "广州": ["guangzhou", "广州"],
        }
        
        patterns = location_patterns.get(location_lower, [location_lower])
        
        filtered = []
        for job in jobs:
            job_location = job.location.lower()
            if any(pattern in job_location for pattern in patterns):
                filtered.append(job)
        
        return filtered

    def parse_search_results(self, markdown: str) -> list[JobPosting]:
        """Parse LinkedIn guest API results into job listings.

        Args:
            markdown: Markdown content from guest API

        Returns:
            List of JobPosting objects
        """
        jobs = []

        # Pattern to match job entries:
        # * [Job Title](URL)
        #   ### Job Title
        #   #### [Company](company_url)
        #   Location
        #   time ago
        
        # Split by list items
        job_blocks = re.split(r'\n\*\s+\[', markdown)
        
        for block in job_blocks[1:]:  # Skip first empty split
            job = self._parse_job_block(block)
            if job:
                jobs.append(job)

        return jobs

    def _parse_job_block(self, block: str) -> Optional[JobPosting]:
        """Parse a single job block from the markdown.

        Args:
            block: Text block for one job listing

        Returns:
            JobPosting or None if parsing fails
        """
        try:
            # Extract job title and URL from the first line
            # Format: Title](URL)
            title_match = re.match(r'([^\]]+)\]\((https?://[^\)]+)\)', block)
            if not title_match:
                return None
                
            title = title_match.group(1).strip()
            url = title_match.group(2)
            
            # URL decode the title (handles Chinese characters)
            title = unquote(title)
            
            # Skip non-job links
            if '/jobs/view/' not in url:
                return None

            # Extract company name
            # Pattern: #### [Company Name](company_url)
            company = "Unknown"
            company_match = re.search(r'####\s+\[([^\]]+)\]', block)
            if company_match:
                company = company_match.group(1).strip()

            # Extract location - usually on its own line after company
            location = "China"
            # Look for location patterns (City, Region, Country)
            location_match = re.search(r'\n\s+([A-Za-z\u4e00-\u9fff][^\n]+(?:China|中国|District|Province|City|Area)[^\n]*)', block, re.IGNORECASE)
            if location_match:
                location = location_match.group(1).strip()
            else:
                # Try simpler pattern
                location_match = re.search(r'\n\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\s,\-]+)\n', block)
                if location_match:
                    loc_text = location_match.group(1).strip()
                    # Filter out non-location text
                    if not any(skip in loc_text.lower() for skip in ['applicant', 'ago', 'week', 'month', 'day', 'hour']):
                        location = loc_text

            # Extract time posted
            posted_text = None
            time_match = re.search(r'(\d+)\s+(hour|day|week|month)s?\s+ago', block, re.IGNORECASE)
            if time_match:
                posted_text = f"{time_match.group(1)} {time_match.group(2)}s ago"

            # Extract tags from title and block
            tags = extract_tags(title + " " + block)

            # Generate unique ID from URL
            job_id = self.generate_job_id(url)

            return JobPosting(
                id=job_id,
                title=title,
                company=company,
                location=location,
                salary_range=None,  # LinkedIn rarely shows salary in listings
                experience=None,
                education=None,
                description=None,
                requirements=[],
                tags=tags[:10],
                posted_date=None,
                url=url,
                source=self.name,
                fetched_at=datetime.now(),
            )
        except Exception as e:
            print(f"Error parsing LinkedIn job block: {e}")
            return None
