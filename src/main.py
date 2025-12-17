"""Main CLI entry point for jobs-cli."""

import asyncio
import logging
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .cache.database import Database
from .client.mcp_client import BrightDataMCP, MCPConnectionError
from .config import get_settings
from .display.ui import (
    display_error,
    display_info,
    display_job_detail,
    display_jobs_table,
    display_stats,
    display_success,
    display_warning,
)
from .models import JobPosting
from .scrapers.zhaopin import ZhaopinScraper
from .scrapers.linkedin import LinkedInScraper
from .utils.parser import parse_salary_min, parse_experience_years

# Global state for verbose/quiet modes
class AppState:
    verbose: bool = False
    quiet: bool = False

state = AppState()


def filter_jobs(
    jobs: list[JobPosting],
    tech: Optional[str] = None,
    salary_min: Optional[int] = None,
    exp: Optional[str] = None,
) -> list[JobPosting]:
    """Filter jobs based on criteria.

    Args:
        jobs: List of jobs to filter
        tech: Comma-separated tech tags to match (any)
        salary_min: Minimum salary in k
        exp: Experience filter (e.g., "3-5" or "5+")

    Returns:
        Filtered list of jobs
    """
    filtered = jobs

    # Filter by tech tags
    if tech:
        tech_tags = [t.strip().lower() for t in tech.split(",")]
        filtered = [
            j for j in filtered
            if any(tag.lower() in [t.lower() for t in j.tags] or
                   any(tag in j.title.lower() or tag in (j.description or "").lower() for tag in tech_tags)
                   for tag in tech_tags)
        ]

    # Filter by minimum salary
    if salary_min is not None:
        new_filtered = []
        for job in filtered:
            job_salary = parse_salary_min(job.salary_range)
            if job_salary is not None and job_salary >= salary_min:
                new_filtered.append(job)
        filtered = new_filtered

    # Filter by experience
    if exp:
        exp_range = parse_experience_years(exp)
        if exp_range:
            req_min, req_max = exp_range
            new_filtered = []
            for job in filtered:
                job_exp = parse_experience_years(job.experience)
                if job_exp:
                    job_min, job_max = job_exp
                    # Job's requirements should overlap with user's experience
                    # If user says "3-5", show jobs that accept 3-5 years
                    if req_max is None:
                        # User specified "5+", show jobs that accept 5+ years
                        if job_max is None or job_max >= req_min:
                            new_filtered.append(job)
                    elif job_max is None:
                        # Job requires "5+", check if user qualifies
                        if req_max >= job_min:
                            new_filtered.append(job)
                    else:
                        # Both have ranges, check overlap
                        if job_min <= req_max and job_max >= req_min:
                            new_filtered.append(job)
                else:
                    # No experience listed, include it
                    new_filtered.append(job)
            filtered = new_filtered

    return filtered

def verbose_callback(value: bool) -> None:
    """Enable verbose output."""
    if value:
        state.verbose = True
        logging.basicConfig(level=logging.DEBUG)


def quiet_callback(value: bool) -> None:
    """Enable quiet mode."""
    if value:
        state.quiet = True


app = typer.Typer(
    name="jobs-cli",
    help="Aggregate software engineering jobs from Chinese job platforms.",
    add_completion=False,
)
console = Console()


async def check_rate_limit(db: Database) -> bool:
    """Check if we're approaching or over the rate limit.
    
    Returns:
        True if OK to proceed, False if should use cache only
    """
    stats = await db.get_monthly_usage()
    settings = get_settings()
    
    # Warning at 80% usage
    if stats.requests_used >= settings.monthly_request_limit * 0.8:
        remaining = stats.requests_remaining
        if remaining <= 0:
            display_warning(
                f"Monthly API limit reached ({stats.requests_used}/{stats.monthly_limit}). "
                "Using cached data only. Limit resets next month."
            )
            return False
        elif remaining <= 500:
            display_warning(
                f"API usage warning: {remaining} requests remaining this month. "
                "Consider using cached data (remove --no-cache)."
            )
    return True


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (job title, keywords)"),
    location: str = typer.Option("Beijing", "-l", "--location", help="Location filter"),
    platform: Optional[str] = typer.Option(None, "-p", "--platform", help="Platform to search (default: zhaopin)"),
    limit: int = typer.Option(20, "-n", "--limit", help="Maximum results to show"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Force refresh, ignore cache"),
    tech: Optional[str] = typer.Option(None, "--tech", "-t", help="Filter by tech/tags (comma-separated, e.g., 'python,django')"),
    salary_min: Optional[int] = typer.Option(None, "--salary-min", help="Minimum salary in k (e.g., 20 for ¥20k)"),
    exp: Optional[str] = typer.Option(None, "--exp", help="Experience filter (e.g., '3-5' or '5+')"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Show detailed output", callback=verbose_callback, is_eager=True),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Minimal output", callback=quiet_callback, is_eager=True),
) -> None:
    """Search for jobs matching the query.
    
    Examples:
        jobs-cli search python                    # Search Zhaopin (default)
        jobs-cli search python -p linkedin        # Search LinkedIn
        jobs-cli search python -p all             # Search all platforms
        jobs-cli search python --tech django      # Filter by tech stack
        jobs-cli search python --salary-min 20    # Min salary ¥20k
        jobs-cli search python --exp 3-5          # 3-5 years experience
    """
    asyncio.run(_search_async(query, location, platform, limit, no_cache, tech, salary_min, exp))


async def _search_async(
    query: str,
    location: str,
    platform: Optional[str],
    limit: int,
    no_cache: bool,
    tech: Optional[str],
    salary_min: Optional[int],
    exp: Optional[str],
) -> None:
    """Async implementation of search command."""
    settings = get_settings()

    if not settings.bright_data_api_token:
        display_error(
            "Bright Data API token not configured.\n"
            "Set BRIGHT_DATA_API_TOKEN environment variable or create a .env file."
        )
        raise typer.Exit(1)

    db = Database()

    # Check cache first (unless --no-cache)
    if not no_cache:
        cached_jobs = await db.search_jobs(query, source=platform, limit=200)  # Get more to allow filtering
        if cached_jobs:
            # Apply filters
            filtered_jobs = filter_jobs(cached_jobs, tech=tech, salary_min=salary_min, exp=exp)
            
            # Build filter info string
            filter_info = []
            if tech:
                filter_info.append(f"tech={tech}")
            if salary_min:
                filter_info.append(f"salary≥¥{salary_min}k")
            if exp:
                filter_info.append(f"exp={exp}")
            filter_str = f" (filters: {', '.join(filter_info)})" if filter_info else ""
            
            display_info(f"Showing {len(filtered_jobs[:limit])} of {len(cached_jobs)} cached results{filter_str}. Use --no-cache to refresh.")
            display_jobs_table(filtered_jobs[:limit], title=f"Jobs matching '{query}'")

            # Show request usage
            stats = await db.get_monthly_usage()
            console.print(f"\n[dim]API Usage: {stats.requests_used}/{stats.monthly_limit} requests this month[/dim]")
            return

    # Check rate limit before making API calls
    if not await check_rate_limit(db):
        # Rate limit reached, try to use any cached data
        all_cached = await db.get_jobs(limit=200)
        if all_cached:
            filtered = filter_jobs(all_cached, tech=tech, salary_min=salary_min, exp=exp)
            if filtered:
                display_info("Showing all cached jobs due to rate limit.")
                display_jobs_table(filtered[:limit], title="Cached Jobs (rate limited)")
                return
        display_error("No cached data available and API limit reached.")
        raise typer.Exit(1)

    # No cache or forced refresh - need to scrape
    all_jobs: list[JobPosting] = []

    # Determine which scrapers to use
    if platform == "all":
        scrapers_to_use = ["zhaopin", "linkedin"]
    elif platform:
        scrapers_to_use = [platform]
    else:
        scrapers_to_use = ["zhaopin"]  # Default to zhaopin

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for scraper_name in scrapers_to_use:
            task = progress.add_task(f"Searching {scraper_name}...", total=None)
            try:
                mcp = BrightDataMCP()
                
                if scraper_name == "zhaopin":
                    scraper = ZhaopinScraper(mcp)
                    result = await scraper.search(query, location)
                elif scraper_name == "linkedin":
                    scraper = LinkedInScraper(mcp)
                    # LinkedIn API needs broader search, then we filter results
                    result = await scraper.search(query, location, filter_location=True)
                else:
                    if not state.quiet:
                        display_info(f"Scraper '{scraper_name}' not yet implemented")
                    progress.remove_task(task)
                    continue

                # Track the request
                await db.increment_request_count(1)

                if result.error:
                    display_warning(f"{scraper_name}: {result.error}")
                elif result.jobs:
                    all_jobs.extend(result.jobs)
                    progress.update(task, description=f"[green]{scraper_name}: found {len(result.jobs)} jobs[/green]")
                else:
                    progress.update(task, description=f"[yellow]{scraper_name}: no jobs found[/yellow]")

            except MCPConnectionError as e:
                display_warning(f"{scraper_name}: Connection failed after retries. Using cached data if available.")
                if state.verbose:
                    console.print(f"[dim]Error details: {e}[/dim]")
            except Exception as e:
                display_warning(f"{scraper_name} error: {e}")
                if state.verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
            finally:
                progress.remove_task(task)

    if not all_jobs:
        display_info("No jobs found. Try a different search query or platform.")
        return

    # Save to cache
    saved_count = await db.save_jobs(all_jobs)
    await db.set_last_refresh("zhaopin")

    # Apply filters
    filtered_jobs = filter_jobs(all_jobs, tech=tech, salary_min=salary_min, exp=exp)
    
    # Build filter info string
    filter_info = []
    if tech:
        filter_info.append(f"tech={tech}")
    if salary_min:
        filter_info.append(f"salary≥¥{salary_min}k")
    if exp:
        filter_info.append(f"exp={exp}")
    filter_str = f" (filters: {', '.join(filter_info)})" if filter_info else ""

    # Display results
    display_jobs_table(filtered_jobs[:limit], title=f"Jobs matching '{query}'{filter_str}")

    # Show stats
    stats = await db.get_monthly_usage()
    filter_note = f" ({len(filtered_jobs)} after filters)" if filter_str else ""
    console.print(f"\n[dim]Found {len(all_jobs)} jobs{filter_note}. API Usage: {stats.requests_used}/{stats.monthly_limit} requests this month[/dim]")


@app.command("list")
def list_jobs(
    source: Optional[str] = typer.Option(None, "-s", "--source", help="Filter by source platform"),
    limit: int = typer.Option(20, "-n", "--limit", help="Maximum results to show"),
    sort_by: str = typer.Option("date", "--sort-by", help="Sort by: date, salary, company"),
    tech: Optional[str] = typer.Option(None, "--tech", "-t", help="Filter by tech/tags (comma-separated)"),
    salary_min: Optional[int] = typer.Option(None, "--salary-min", help="Minimum salary in k"),
    exp: Optional[str] = typer.Option(None, "--exp", help="Experience filter (e.g., '3-5' or '5+')"),
) -> None:
    """List cached jobs."""
    asyncio.run(_list_async(source, limit, sort_by, tech, salary_min, exp))


async def _list_async(
    source: Optional[str],
    limit: int,
    sort_by: str,
    tech: Optional[str],
    salary_min: Optional[int],
    exp: Optional[str],
) -> None:
    """Async implementation of list command."""
    db = Database()
    jobs = await db.get_jobs(source=source, limit=500)  # Get more to allow filtering

    if not jobs:
        display_info("No jobs in cache. Run 'jobs-cli search <query>' to fetch jobs.")
        return

    # Apply filters
    filtered_jobs = filter_jobs(jobs, tech=tech, salary_min=salary_min, exp=exp)

    # Sort if needed
    if sort_by == "company":
        filtered_jobs.sort(key=lambda j: j.company.lower())
    elif sort_by == "salary":
        # Sort by salary (jobs with salary first, then by amount descending)
        def salary_sort_key(j: JobPosting) -> tuple[bool, int]:
            sal = parse_salary_min(j.salary_range)
            return (j.salary_range is None, -(sal or 0))
        filtered_jobs.sort(key=salary_sort_key)

    # Build filter info
    filter_info = []
    if tech:
        filter_info.append(f"tech={tech}")
    if salary_min:
        filter_info.append(f"salary≥¥{salary_min}k")
    if exp:
        filter_info.append(f"exp={exp}")
    filter_str = f" ({', '.join(filter_info)})" if filter_info else ""
    
    title = f"Cached Jobs{filter_str}"
    if len(filtered_jobs) < len(jobs):
        display_info(f"Showing {len(filtered_jobs[:limit])} of {len(jobs)} total jobs (filtered)")
    
    display_jobs_table(filtered_jobs[:limit], title=title, show_source=True)


@app.command()
def show(
    job_id: str = typer.Argument(..., help="Job ID or number from list"),
    open_url: bool = typer.Option(False, "--open", "-o", help="Open job URL in browser"),
) -> None:
    """Show detailed information about a job."""
    asyncio.run(_show_async(job_id, open_url))


async def _show_async(job_id: str, open_url: bool) -> None:
    """Async implementation of show command."""
    import webbrowser

    db = Database()

    # Try to find by ID first
    job = await db.get_job(job_id)

    if not job:
        # Maybe it's a number from the list?
        try:
            idx = int(job_id) - 1
            jobs = await db.get_jobs(limit=100)
            if 0 <= idx < len(jobs):
                job = jobs[idx]
        except ValueError:
            pass

    if not job:
        display_error(f"Job not found: {job_id}")
        raise typer.Exit(1)

    display_job_detail(job)

    if open_url:
        console.print(f"\n[dim]Opening {job.url} in browser...[/dim]")
        webbrowser.open(job.url)


@app.command()
def stats() -> None:
    """Show usage statistics and cache information."""
    asyncio.run(_stats_async())


async def _stats_async() -> None:
    """Async implementation of stats command."""
    db = Database()
    settings = get_settings()

    # Get request stats
    request_stats = await db.get_monthly_usage()

    # Get job counts per source
    job_counts = {}
    last_refresh = {}
    for source in settings.enabled_scrapers:
        job_counts[source] = await db.get_job_count(source)
        last_refresh[source] = await db.get_last_refresh(source)

    display_stats(request_stats, job_counts, last_refresh)


@app.command()
def config(
    show_config: bool = typer.Option(False, "--show", help="Show current configuration"),
) -> None:
    """Manage configuration."""
    if show_config:
        settings = get_settings()
        console.print("\n[bold]Current Configuration:[/bold]\n")
        console.print(f"  API Token: {'[green]configured[/green]' if settings.bright_data_api_token else '[red]not set[/red]'}")
        console.print(f"  Cache Directory: {settings.cache_dir}")
        console.print(f"  Cache Expiry: {settings.cache_expiry_hours} hours")
        console.print(f"  Default Location: {settings.default_location}")
        console.print(f"  Enabled Scrapers: {', '.join(settings.enabled_scrapers)}")
        console.print(f"\n  Database: {settings.database_path}")
    else:
        console.print("Use --show to display current configuration.")
        console.print("Configuration is managed via environment variables and .env file.")


@app.command()
def export(
    output: str = typer.Argument(..., help="Output file path (e.g., jobs.json or jobs.csv)"),
    format: Optional[str] = typer.Option(None, "-f", "--format", help="Output format: json or csv (auto-detected from filename)"),
    source: Optional[str] = typer.Option(None, "-s", "--source", help="Filter by source platform"),
    tech: Optional[str] = typer.Option(None, "--tech", "-t", help="Filter by tech/tags (comma-separated)"),
    salary_min: Optional[int] = typer.Option(None, "--salary-min", help="Minimum salary in k"),
    exp: Optional[str] = typer.Option(None, "--exp", help="Experience filter (e.g., '3-5' or '5+')"),
    limit: int = typer.Option(1000, "-n", "--limit", help="Maximum jobs to export"),
) -> None:
    """Export jobs to JSON or CSV file."""
    asyncio.run(_export_async(output, format, source, tech, salary_min, exp, limit))


async def _export_async(
    output: str,
    format: Optional[str],
    source: Optional[str],
    tech: Optional[str],
    salary_min: Optional[int],
    exp: Optional[str],
    limit: int,
) -> None:
    """Async implementation of export command."""
    import csv
    import json
    from pathlib import Path

    db = Database()
    jobs = await db.get_jobs(source=source, limit=limit)

    if not jobs:
        display_info("No jobs in cache to export.")
        return

    # Apply filters
    filtered_jobs = filter_jobs(jobs, tech=tech, salary_min=salary_min, exp=exp)

    if not filtered_jobs:
        display_info("No jobs match the specified filters.")
        return

    # Determine format
    output_path = Path(output)
    if format is None:
        if output_path.suffix.lower() == ".json":
            format = "json"
        elif output_path.suffix.lower() == ".csv":
            format = "csv"
        else:
            display_error("Cannot determine format from filename. Use --format json or --format csv")
            raise typer.Exit(1)

    # Export
    if format == "json":
        data = [job.model_dump(mode="json") for job in filtered_jobs]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif format == "csv":
        fieldnames = ["title", "company", "location", "salary_range", "experience", "education", "url", "source", "tags"]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for job in filtered_jobs:
                writer.writerow({
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "salary_range": job.salary_range or "",
                    "experience": job.experience or "",
                    "education": job.education or "",
                    "url": job.url,
                    "source": job.source,
                    "tags": ", ".join(job.tags),
                })
    else:
        display_error(f"Unknown format: {format}. Use json or csv.")
        raise typer.Exit(1)

    display_success(f"Exported {len(filtered_jobs)} jobs to {output_path}")


@app.command()
def refresh(
    platform: Optional[str] = typer.Option(None, "-p", "--platform", help="Platform to refresh (default: all enabled)"),
    query: str = typer.Option("软件工程师", "-q", "--query", help="Search query to use for refresh"),
    location: str = typer.Option("Beijing", "-l", "--location", help="Location filter"),
) -> None:
    """Refresh job listings from platforms."""
    asyncio.run(_refresh_async(platform, query, location))


async def _refresh_async(
    platform: Optional[str],
    query: str,
    location: str,
) -> None:
    """Async implementation of refresh command."""
    settings = get_settings()

    if not settings.bright_data_api_token:
        display_error(
            "Bright Data API token not configured.\n"
            "Set BRIGHT_DATA_API_TOKEN environment variable."
        )
        raise typer.Exit(1)

    db = Database()
    
    # Determine which scrapers to use
    platforms_to_refresh = [platform] if platform else ["zhaopin"]  # Only zhaopin works reliably
    total_new_jobs = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for scraper_name in platforms_to_refresh:
            if scraper_name == "zhaopin":
                task = progress.add_task(f"Refreshing {scraper_name}...", total=None)
                try:
                    mcp = BrightDataMCP()
                    scraper = ZhaopinScraper(mcp)
                    result = await scraper.search(query, location)

                    # Track the request
                    await db.increment_request_count(1)

                    if result.error:
                        progress.update(task, description=f"[red]{scraper_name}: {result.error}[/red]")
                    elif result.jobs:
                        # Count new vs updated
                        existing_count = await db.get_job_count(scraper_name)
                        saved_count = await db.save_jobs(result.jobs)
                        await db.set_last_refresh(scraper_name)
                        new_count = await db.get_job_count(scraper_name) - existing_count
                        total_new_jobs += max(0, new_count)
                        progress.update(task, description=f"[green]{scraper_name}: {len(result.jobs)} jobs (cached)[/green]")
                    else:
                        progress.update(task, description=f"[yellow]{scraper_name}: no jobs found[/yellow]")

                except Exception as e:
                    progress.update(task, description=f"[red]{scraper_name}: error - {e}[/red]")
                finally:
                    progress.remove_task(task)
            else:
                display_warning(f"Scraper '{scraper_name}' not yet implemented")

    # Show summary
    stats = await db.get_monthly_usage()
    total_cached = await db.get_job_count()
    display_success(f"Refresh complete. {total_cached} total jobs cached.")
    console.print(f"[dim]API Usage: {stats.requests_used}/{stats.monthly_limit} requests this month[/dim]")


@app.command("clear-cache")
def clear_cache(
    older_than: int = typer.Option(30, "--older-than", "-d", help="Delete jobs older than N days"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Clear old jobs from the cache."""
    asyncio.run(_clear_cache_async(older_than, force))


async def _clear_cache_async(older_than: int, force: bool) -> None:
    """Async implementation of clear-cache command."""
    db = Database()
    
    # Get current count
    current_count = await db.get_job_count()
    
    if current_count == 0:
        display_info("Cache is already empty.")
        return
    
    if not force:
        console.print(f"\nThis will delete jobs older than {older_than} days from the cache.")
        console.print(f"Current cache has {current_count} jobs.")
        confirm = typer.confirm("Continue?")
        if not confirm:
            display_info("Cancelled.")
            return
    
    deleted = await db.delete_old_jobs(days=older_than)
    remaining = await db.get_job_count()
    
    display_success(f"Deleted {deleted} old jobs. {remaining} jobs remaining in cache.")


@app.command()
def tui() -> None:
    """Launch interactive TUI mode.
    
    An interactive terminal interface for browsing and searching jobs.
    
    Keyboard shortcuts:
        j/k     - Move up/down in job list
        Enter   - Select job / Open in browser
        /       - Focus search input
        r       - Refresh jobs
        q       - Quit
    
    Commands (type in command bar):
        search <query>  - Search for jobs
        list            - List all cached jobs
        refresh         - Refresh from API
        show <n>        - Show job #n
        open            - Open selected job in browser
        stats           - Show statistics
        quit            - Exit
    """
    from .tui.app import run_tui
    run_tui()


@app.command()
def test_connection() -> None:
    """Test the connection to Bright Data MCP."""
    asyncio.run(_test_connection_async())


async def _test_connection_async() -> None:
    """Async implementation of test-connection command."""
    settings = get_settings()

    if not settings.bright_data_api_token:
        display_error(
            "Bright Data API token not configured.\n"
            "Set BRIGHT_DATA_API_TOKEN environment variable."
        )
        raise typer.Exit(1)

    console.print("Testing connection to Bright Data MCP...")

    try:
        mcp = BrightDataMCP()
        tools = await mcp.list_available_tools()
        display_success("Connection successful!")
        console.print(f"\n[bold]Available tools:[/bold]")
        for tool in tools:
            console.print(f"  • {tool}")
    except Exception as e:
        display_error(f"Connection failed: {e}")
        raise typer.Exit(1)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
