"""Pydantic data models for job postings and queries."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class JobPosting(BaseModel):
    """A job posting from a Chinese job platform."""

    id: str = Field(description="Unique identifier (usually from URL)")
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: str = Field(default="Beijing", description="Job location/district")
    salary_range: Optional[str] = Field(default=None, description="Salary range, e.g., '20k-35k'")
    experience: Optional[str] = Field(default=None, description="Required experience")
    education: Optional[str] = Field(default=None, description="Education requirement")
    description: Optional[str] = Field(default=None, description="Full job description")
    requirements: list[str] = Field(default_factory=list, description="List of requirements")
    tags: list[str] = Field(default_factory=list, description="Tech stack/skill tags")
    posted_date: Optional[datetime] = Field(default=None, description="When the job was posted")
    url: str = Field(description="Original job posting URL")
    source: str = Field(description="Platform name (boss_zhipin, zhaopin, etc.)")
    fetched_at: datetime = Field(default_factory=datetime.now, description="When we scraped this")
    is_active: bool = Field(default=True, description="Whether the job is still active")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class SearchQuery(BaseModel):
    """Parameters for a job search."""

    query: str = Field(description="Search query (job title, keywords)")
    location: str = Field(default="Beijing", description="City/location filter")
    salary_min: Optional[int] = Field(default=None, description="Minimum salary in k (e.g., 20 for 20k)")
    platforms: list[str] = Field(default_factory=list, description="Platforms to search (empty = all)")
    limit: int = Field(default=20, description="Max results to return")
    page: int = Field(default=1, description="Page number for pagination")


class ScraperResult(BaseModel):
    """Result from a scraper operation."""

    jobs: list[JobPosting] = Field(default_factory=list, description="List of jobs found")
    total_count: int = Field(default=0, description="Total jobs available (may be > len(jobs))")
    page: int = Field(default=1, description="Current page")
    has_more: bool = Field(default=False, description="Whether more pages are available")
    source: str = Field(description="Which scraper produced this result")
    error: Optional[str] = Field(default=None, description="Error message if scraping failed")


class RequestStats(BaseModel):
    """Statistics about API request usage."""

    month: str = Field(description="Month in YYYY-MM format")
    requests_used: int = Field(default=0, description="Requests used this month")
    monthly_limit: int = Field(default=5000, description="Monthly request limit")

    @property
    def requests_remaining(self) -> int:
        """Calculate remaining requests."""
        return max(0, self.monthly_limit - self.requests_used)

    @property
    def usage_percentage(self) -> float:
        """Calculate usage as percentage."""
        return (self.requests_used / self.monthly_limit) * 100 if self.monthly_limit > 0 else 0
