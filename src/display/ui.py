"""Rich terminal UI components for displaying job information."""

from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models import JobPosting, RequestStats

console = Console()


def display_jobs_table(
    jobs: list[JobPosting],
    title: str = "Job Listings",
    show_source: bool = True,
) -> None:
    """Display jobs in a formatted table.

    Args:
        jobs: List of jobs to display
        title: Table title
        show_source: Whether to show the source column
    """
    if not jobs:
        console.print("[yellow]No jobs found.[/yellow]")
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")

    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="white", max_width=30)
    table.add_column("Company", style="green", max_width=20)
    table.add_column("Location", style="blue", max_width=15)
    table.add_column("Salary (RMB)", style="yellow", max_width=14)
    if show_source:
        table.add_column("Source", style="magenta", max_width=12)

    for i, job in enumerate(jobs, 1):
        # Format salary with currency indicator
        salary_display = f"¥{job.salary_range}" if job.salary_range else "-"
        row = [
            str(i),
            _truncate(job.title, 30),
            _truncate(job.company, 20),
            _truncate(job.location, 15),
            salary_display,
        ]
        if show_source:
            row.append(job.source)
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Showing {len(jobs)} jobs. Use 'jobs-cli show <#>' to view details.[/dim]")


def display_job_detail(job: JobPosting) -> None:
    """Display detailed information about a single job.

    Args:
        job: The job to display
    """
    # Header
    title_text = Text(job.title, style="bold white")
    company_text = Text(f" @ {job.company}", style="green")

    header = Text()
    header.append_text(title_text)
    header.append_text(company_text)

    # Build content sections
    content_parts = []

    # Basic info
    content_parts.append(f"[blue]Location:[/blue]  {job.location}")
    if job.salary_range:
        content_parts.append(f"[yellow]Salary:[/yellow]   ¥{job.salary_range}/month")
    if job.experience:
        content_parts.append(f"[cyan]Experience:[/cyan] {job.experience}")
    if job.education:
        content_parts.append(f"[cyan]Education:[/cyan]  {job.education}")

    # Posted date
    if job.posted_date:
        age = _format_relative_date(job.posted_date)
        content_parts.append(f"[dim]Posted:[/dim]    {age}")

    content_parts.append(f"[magenta]Source:[/magenta]    {job.source}")
    content_parts.append("")

    # Tags
    if job.tags:
        tags_str = " ".join(f"[{tag}]" for tag in job.tags[:10])
        content_parts.append(f"[bold]Tech Stack:[/bold]\n  {tags_str}")
        content_parts.append("")

    # Description
    if job.description:
        desc = _truncate(job.description, 500)
        content_parts.append(f"[bold]Description:[/bold]\n  {desc}")
        content_parts.append("")

    # Requirements
    if job.requirements:
        content_parts.append("[bold]Requirements:[/bold]")
        for req in job.requirements[:8]:
            content_parts.append(f"  • {_truncate(req, 70)}")
        content_parts.append("")

    # URL
    content_parts.append(f"[dim]URL: {job.url}[/dim]")

    panel = Panel(
        "\n".join(content_parts),
        title=header,
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def display_stats(
    request_stats: RequestStats,
    job_counts: dict[str, int],
    last_refresh: dict[str, Optional[datetime]],
) -> None:
    """Display usage statistics.

    Args:
        request_stats: Request usage statistics
        job_counts: Dictionary of job counts per source
        last_refresh: Dictionary of last refresh times per source
    """
    # Request usage panel
    usage_pct = request_stats.usage_percentage
    if usage_pct > 80:
        usage_style = "red"
    elif usage_pct > 50:
        usage_style = "yellow"
    else:
        usage_style = "green"

    usage_bar = _create_progress_bar(usage_pct)

    usage_content = [
        f"[bold]Monthly API Usage ({request_stats.month})[/bold]",
        "",
        f"  {usage_bar} [{usage_style}]{usage_pct:.1f}%[/{usage_style}]",
        f"  {request_stats.requests_used:,} / {request_stats.monthly_limit:,} requests",
        f"  [dim]{request_stats.requests_remaining:,} remaining[/dim]",
    ]

    console.print(Panel("\n".join(usage_content), title="API Usage", border_style="cyan"))

    # Cache statistics table
    table = Table(title="Cache Statistics", show_header=True, header_style="bold cyan")
    table.add_column("Source", style="magenta")
    table.add_column("Jobs", style="green", justify="right")
    table.add_column("Last Refresh", style="dim")

    total_jobs = 0
    for source in sorted(job_counts.keys()):
        count = job_counts[source]
        total_jobs += count
        refresh_time = last_refresh.get(source)
        refresh_str = _format_relative_date(refresh_time) if refresh_time else "Never"
        table.add_row(source, str(count), refresh_str)

    table.add_row("[bold]Total[/bold]", f"[bold]{total_jobs}[/bold]", "")
    console.print(table)


def display_error(message: str, title: str = "Error") -> None:
    """Display an error message.

    Args:
        message: Error message
        title: Panel title
    """
    console.print(Panel(f"[red]{message}[/red]", title=title, border_style="red"))


def display_success(message: str, title: str = "Success") -> None:
    """Display a success message.

    Args:
        message: Success message
        title: Panel title
    """
    console.print(Panel(f"[green]{message}[/green]", title=title, border_style="green"))


def display_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def display_info(message: str) -> None:
    """Display an info message."""
    console.print(f"[blue]Info:[/blue] {message}")


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _format_relative_date(dt: datetime) -> str:
    """Format a datetime as a relative string (e.g., '2 days ago')."""
    if not dt:
        return "Unknown"

    now = datetime.now()
    diff = now - dt

    if diff.days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            minutes = diff.seconds // 60
            return f"{minutes} minutes ago" if minutes > 1 else "Just now"
        return f"{hours} hours ago" if hours > 1 else "1 hour ago"
    elif diff.days == 1:
        return "Yesterday"
    elif diff.days < 7:
        return f"{diff.days} days ago"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} weeks ago" if weeks > 1 else "1 week ago"
    else:
        return dt.strftime("%Y-%m-%d")


def _create_progress_bar(percentage: float, width: int = 20) -> str:
    """Create a text-based progress bar."""
    filled = int(width * percentage / 100)
    empty = width - filled
    return f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim]"
