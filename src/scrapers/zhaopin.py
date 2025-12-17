"""Zhaopin (智联招聘) job scraper."""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin

from . import register_scraper
from .base import BaseScraper
from ..models import JobPosting, ScraperResult
from ..utils.parser import extract_salary, extract_experience, extract_tags, normalize_location


# Zhaopin city codes
CITY_CODES = {
    "beijing": "530",
    "北京": "530",
    "shanghai": "538",
    "上海": "538",
    "guangzhou": "763",
    "广州": "763",
    "shenzhen": "765",
    "深圳": "765",
}


@register_scraper("zhaopin")
class ZhaopinScraper(BaseScraper):
    """Scraper for Zhaopin (智联招聘) job platform."""

    name = "zhaopin"
    base_url = "https://sou.zhaopin.com/"

    def build_search_url(
        self,
        query: str,
        location: str = "Beijing",
        page: int = 1,
    ) -> str:
        """Build the Zhaopin search URL.

        Args:
            query: Search query
            location: City name
            page: Page number

        Returns:
            Full search URL
        """
        # Get city code
        city_code = CITY_CODES.get(location.lower(), CITY_CODES.get("beijing"))

        # Build URL with parameters
        # jl = city code, kw = keyword, p = page, kt = search type (3 = title)
        params = f"?jl={city_code}&kw={quote(query)}&p={page}&kt=3"
        return f"{self.base_url}{params}"

    async def search(
        self,
        query: str,
        location: str = "Beijing",
        page: int = 1,
    ) -> ScraperResult:
        """Search for jobs on Zhaopin.

        Args:
            query: Search query
            location: City filter
            page: Page number

        Returns:
            ScraperResult with jobs found
        """
        url = self.build_search_url(query, location, page)

        try:
            markdown = await self.scrape_url(url)
            jobs = self.parse_search_results(markdown)

            # Determine if there are more pages
            has_more = len(jobs) >= 15  # Zhaopin typically shows 15-20 jobs per page

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
        """Get detailed job information.

        Args:
            job_url: URL of the job posting

        Returns:
            JobPosting with full details
        """
        # For now, we get enough info from search results
        # Can implement detail page scraping later if needed
        return None

    def parse_search_results(self, markdown: str) -> list[JobPosting]:
        """Parse Zhaopin search results markdown into job listings.

        Args:
            markdown: Markdown content from search results page

        Returns:
            List of JobPosting objects
        """
        jobs = []

        # Split by job entries - each job starts with a link in markdown format
        # Pattern: [Job Title](URL)
        # Followed by salary, location, experience, education, company info

        # Find all job blocks - they follow a consistent pattern
        # [Title](url) ... salary ... location ... experience ... education ... [Company](url)

        # Pattern to find job title links
        job_pattern = r'\[([^\]]+)\]\((https?://(?:www\.)?zhaopin\.com/jobdetail/[^\)]+)\)'

        matches = list(re.finditer(job_pattern, markdown))

        for i, match in enumerate(matches):
            title = match.group(1).strip()
            url = match.group(2)

            # Skip navigation links and non-job links
            if any(skip in title.lower() for skip in ['首页', '职位推荐', '登录', '注册', '收藏', '投递']):
                continue

            # Get the text block after this job title until next job or end
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            block = markdown[start_pos:end_pos]

            # Extract job details from the block
            job = self._parse_job_block(title, url, block)
            if job:
                jobs.append(job)

        return jobs

    def _parse_job_block(self, title: str, url: str, block: str) -> Optional[JobPosting]:
        """Parse a single job block from the markdown.

        Args:
            title: Job title
            url: Job URL
            block: Text block containing job details

        Returns:
            JobPosting or None if parsing fails
        """
        try:
            # Extract salary - patterns like "1.5-3万", "6000-9000元", "2-3万·16薪"
            salary = None
            salary_patterns = [
                r'(\d+(?:\.\d+)?-\d+(?:\.\d+)?万(?:·\d+薪)?)',  # 1.5-3万 or 2-3万·16薪
                r'(\d{4,}-\d{4,}元)',  # 6000-9000元
                r'(\d+(?:\.\d+)?-\d+(?:\.\d+)?万)',  # 1.5-3万
            ]
            for pattern in salary_patterns:
                salary_match = re.search(pattern, block)
                if salary_match:
                    salary = salary_match.group(1)
                    break

            # Normalize salary to k format
            if salary:
                salary = self._normalize_salary(salary)

            # Extract location - pattern like "北京·海淀" or "北京·海淀·上地"
            location = "Beijing"
            location_match = re.search(r'北京[·\s]*([^\s\n]+)?', block)
            if location_match:
                district = location_match.group(1) if location_match.group(1) else ""
                location = f"Beijing, {district}".rstrip(", ")

            # Extract experience - patterns like "1-3年", "经验不限", "5-10年"
            experience = None
            exp_match = re.search(r'(\d+-\d+年|经验不限|\d+年以上)', block)
            if exp_match:
                exp_text = exp_match.group(1)
                if exp_text == "经验不限":
                    experience = "Entry Level"
                else:
                    experience = exp_text.replace("年", " years").replace("以上", "+")

            # Extract education - patterns like "本科", "硕士", "大专"
            education = None
            edu_match = re.search(r'(本科|硕士|博士|大专|学历不限)', block)
            if edu_match:
                edu_map = {
                    "本科": "Bachelor",
                    "硕士": "Master",
                    "博士": "PhD",
                    "大专": "Associate",
                    "学历不限": "Not Required",
                }
                education = edu_map.get(edu_match.group(1), edu_match.group(1))

            # Extract company name - pattern: [Company Name](company_url)
            company = "Unknown"
            company_match = re.search(r'\[([^\]]+)\]\([^\)]*companydetail[^\)]*\)', block)
            if company_match:
                company = company_match.group(1).strip()

            # Extract tags/skills from the block
            tags = extract_tags(block)

            # Also look for explicit skill tags in the markdown
            skill_tags = re.findall(r'(?:^|\s)(Python|Java|C\+\+|Go|MySQL|Redis|Django|Flask|Docker|Kubernetes|Spring|PostgreSQL|MongoDB|Oracle|JavaScript|Vue|React|Node\.js)(?:\s|$)', block, re.IGNORECASE)
            for tag in skill_tags:
                if tag not in tags:
                    tags.append(tag)

            # Generate unique ID from URL
            job_id = self.generate_job_id(url)

            return JobPosting(
                id=job_id,
                title=title,
                company=company,
                location=location,
                salary_range=salary,
                experience=experience,
                education=education,
                description=None,  # Would need to fetch detail page
                requirements=[],
                tags=tags[:10],  # Limit to 10 tags
                posted_date=None,
                url=url,
                source=self.name,
                fetched_at=datetime.now(),
            )
        except Exception as e:
            # Log error but don't fail
            print(f"Error parsing job block: {e}")
            return None

    def _normalize_salary(self, salary_str: str) -> str:
        """Normalize salary string to k format (monthly).

        Args:
            salary_str: Raw salary string like "1.5-3万" or "6000-9000元" or "2-3万·16薪"

        Returns:
            Normalized salary like "15k-30k" (monthly)
        """
        # Handle 万 (10k) format
        wan_match = re.search(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)万', salary_str)
        if wan_match:
            low = float(wan_match.group(1)) * 10
            high = float(wan_match.group(2)) * 10
            return f"{int(low)}k-{int(high)}k"

        # Handle 元 format (assume monthly)
        yuan_match = re.search(r'(\d+)-(\d+)元', salary_str)
        if yuan_match:
            low = int(yuan_match.group(1)) // 1000
            high = int(yuan_match.group(2)) // 1000
            return f"{low}k-{high}k"

        return salary_str

    def parse_job_detail(self, markdown: str, job: JobPosting) -> JobPosting:
        """Parse job detail page to get full description.

        Args:
            markdown: Detail page markdown
            job: Existing job object to update

        Returns:
            Updated JobPosting
        """
        # Extract description section if present
        # This would need to be implemented based on detail page structure
        return job
