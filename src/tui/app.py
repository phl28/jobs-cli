"""Main TUI application for jobs-cli."""

import asyncio
import webbrowser
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, Center, Middle
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
)

from ..cache.database import Database
from ..client.mcp_client import BrightDataMCP
from ..config import get_settings
from ..models import JobPosting
from ..scrapers.zhaopin import ZhaopinScraper
from ..scrapers.linkedin import LinkedInScraper
from ..utils.parser import parse_salary_min, parse_experience_years


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
                    if req_max is None:
                        if job_max is None or job_max >= req_min:
                            new_filtered.append(job)
                    elif job_max is None:
                        if req_max >= job_min:
                            new_filtered.append(job)
                    else:
                        if job_min <= req_max and job_max >= req_min:
                            new_filtered.append(job)
                else:
                    # No experience listed, include it
                    new_filtered.append(job)
            filtered = new_filtered

    return filtered


class StatusBar(Static):
    """Status bar showing API usage and cache stats."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_usage = "0/5000"
        self.job_count = 0
        self.last_search = ""
        self.current_page = 1
        self.has_more = False
        self.platform = "zhaopin"
        self.location = "Beijing"
        self.filters: dict = {}

    def update_stats(
        self,
        api_used: int,
        api_limit: int,
        job_count: int,
        last_search: str = "",
        current_page: int = 1,
        has_more: bool = False,
        platform: str = "zhaopin",
        location: str = "Beijing",
        filters: Optional[dict] = None,
    ) -> None:
        """Update the status bar with new stats."""
        self.api_usage = f"{api_used}/{api_limit}"
        self.job_count = job_count
        self.last_search = last_search
        self.current_page = current_page
        self.has_more = has_more
        self.platform = platform
        self.location = location
        self.filters = filters or {}
        self.refresh_display()

    def refresh_display(self) -> None:
        """Refresh the status bar display."""
        search_info = f" | Search: '{self.last_search}'" if self.last_search else ""
        page_info = f" | Page {self.current_page}" if self.last_search else ""
        more_info = " [n=more]" if self.has_more else ""
        platform_info = f" | [{self.platform}]"
        location_info = f" @ {self.location}"
        
        # Build filter info
        filter_parts = []
        if self.filters.get("tech"):
            filter_parts.append(f"tech={self.filters['tech']}")
        if self.filters.get("salary_min"):
            filter_parts.append(f"sal>={self.filters['salary_min']}k")
        if self.filters.get("exp"):
            filter_parts.append(f"exp={self.filters['exp']}")
        filter_info = f" | Filters: {', '.join(filter_parts)}" if filter_parts else ""
        
        self.update(f"Jobs: {self.job_count} | API: {self.api_usage}{platform_info}{location_info}{search_info}{page_info}{filter_info}{more_info}")


class JobDetail(Static):
    """Panel showing job details."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.job: Optional[JobPosting] = None

    def show_job(self, job: JobPosting) -> None:
        """Display job details."""
        from rich.markup import escape
        
        self.job = job
        
        # Format salary
        salary = f"[green]¥{job.salary_range}[/green]" if job.salary_range else "[dim]Not specified[/dim]"
        
        # Format tags
        tags = ", ".join(job.tags[:8]) if job.tags else "None"
        
        # Escape the URL to prevent markup interpretation
        escaped_url = escape(job.url)
        
        content = f"""[bold]{escape(job.title)}[/bold]
[cyan]{escape(job.company)}[/cyan]

[bold]Location:[/bold] {escape(job.location)}
[bold]Salary:[/bold] {salary}
[bold]Experience:[/bold] {job.experience or 'Not specified'}
[bold]Education:[/bold] {job.education or 'Not specified'}

[bold]Tags:[/bold] {tags}

[bold]URL:[/bold] {escaped_url}

[dim]Press 'o' or Enter to open in browser[/dim]"""
        
        self.update(content)

    def clear(self) -> None:
        """Clear the job detail view."""
        self.job = None
        self.update("[dim]Select a job to view details[/dim]")


class CommandInput(Input):
    """Command input field at the bottom."""

    def __init__(self, **kwargs) -> None:
        super().__init__(placeholder="Type command (? for help): search <query>, list, refresh, quit", **kwargs)


class HelpModal(ModalScreen):
    """Modal screen showing keyboard shortcuts and commands."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
    ]

    CSS = """
    HelpModal {
        align: center middle;
    }

    #help-container {
        width: 70;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        color: $text;
        padding-bottom: 1;
        border-bottom: solid $primary;
        margin-bottom: 1;
    }

    .help-section {
        margin-bottom: 1;
    }

    .help-section-title {
        text-style: bold;
        color: $accent;
    }

    .help-row {
        padding-left: 2;
    }

    .help-key {
        color: $warning;
        text-style: bold;
        width: 15;
    }

    .help-desc {
        color: $text-muted;
    }

    #help-footer {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        border-top: solid $primary;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the help modal content."""
        with Container(id="help-container"):
            yield Static("Jobs CLI - Keyboard Shortcuts", id="help-title")
            
            # Navigation section
            yield Static("[bold cyan]Navigation[/bold cyan]", classes="help-section-title")
            yield Static("[yellow]j / ↓[/yellow]        Move down in job list", classes="help-row")
            yield Static("[yellow]k / ↑[/yellow]        Move up in job list", classes="help-row")
            yield Static("[yellow]Enter[/yellow]        Select job / Open in browser", classes="help-row")
            yield Static("[yellow]Esc[/yellow]          Clear selection", classes="help-row")
            yield Static("")
            
            # Actions section
            yield Static("[bold cyan]Actions[/bold cyan]", classes="help-section-title")
            yield Static("[yellow]/[/yellow]            Focus search input", classes="help-row")
            yield Static("[yellow]r[/yellow]            Refresh jobs from API", classes="help-row")
            yield Static("[yellow]n[/yellow]            Load next page of results", classes="help-row")
            yield Static("[yellow]o[/yellow]            Open selected job in browser", classes="help-row")
            yield Static("[yellow]?[/yellow]            Show this help", classes="help-row")
            yield Static("[yellow]q[/yellow]            Quit application", classes="help-row")
            yield Static("")
            
            # Commands section
            yield Static("[bold cyan]Commands (type in command bar)[/bold cyan]", classes="help-section-title")
            yield Static("[yellow]search <query>[/yellow]   Search for jobs", classes="help-row")
            yield Static("[yellow]list[/yellow]             List all cached jobs", classes="help-row")
            yield Static("[yellow]more / next[/yellow]      Load next page of results", classes="help-row")
            yield Static("[yellow]show <n>[/yellow]         Show job #n details", classes="help-row")
            yield Static("[yellow]open[/yellow]             Open selected job", classes="help-row")
            yield Static("[yellow]refresh[/yellow]          Refresh from API", classes="help-row")
            yield Static("[yellow]stats[/yellow]            Show API usage stats", classes="help-row")
            yield Static("[yellow]quit[/yellow]             Exit application", classes="help-row")
            yield Static("")
            
            # Platform & filter commands
            yield Static("[bold cyan]Platform & Filters[/bold cyan]", classes="help-section-title")
            yield Static("[yellow]platform <p>[/yellow]     Set platform: zhaopin, linkedin, all", classes="help-row")
            yield Static("[yellow]location <loc>[/yellow]   Set location (e.g., Beijing, Shanghai)", classes="help-row")
            yield Static("[yellow]filter tech=<t>[/yellow]  Filter by tech (e.g., python,django)", classes="help-row")
            yield Static("[yellow]filter salary=<n>[/yellow] Filter by min salary in k", classes="help-row")
            yield Static("[yellow]filter exp=<e>[/yellow]   Filter by experience (e.g., 3-5, 5+)", classes="help-row")
            yield Static("[yellow]filter clear[/yellow]     Clear all filters", classes="help-row")
            
            yield Static("Press [bold]Esc[/bold], [bold]q[/bold], or [bold]?[/bold] to close", id="help-footer")


class JobsApp(App):
    """Interactive TUI for browsing jobs."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 3fr 1fr;
        grid-rows: 1fr auto auto;
    }

    #job-table {
        column-span: 1;
        row-span: 1;
        border: solid green;
    }

    #job-detail {
        column-span: 1;
        row-span: 1;
        border: solid cyan;
        padding: 1;
    }

    #status-bar {
        column-span: 2;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }

    #command-input {
        column-span: 2;
        dock: bottom;
    }

    DataTable {
        height: 100%;
    }

    DataTable > .datatable--cursor {
        background: $accent;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "select_job", "Select"),
        Binding("escape", "clear_detail", "Clear", show=False),
        Binding("o", "open_job", "Open"),
        Binding("/", "focus_search", "Search"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "load_more", "More"),
        Binding("?", "show_help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[JobPosting] = []
        self.selected_job: Optional[JobPosting] = None
        self.current_search: str = ""
        self.current_page: int = 1
        self.has_more: bool = False
        self.db: Optional[Database] = None
        self.detail_visible = False
        # New: platform, location, filters
        self.current_platform: str = "zhaopin"
        self.current_location: str = "Beijing"
        self.filters: dict = {}  # tech, salary_min, exp

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)
        yield DataTable(id="job-table")
        yield JobDetail(id="job-detail")
        yield StatusBar(id="status-bar")
        yield CommandInput(id="command-input")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app on mount."""
        self.db = Database()
        
        # Setup table
        table = self.query_one("#job-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("#", "Title", "Company", "Salary", "Location", "Source")
        
        # Clear detail panel
        detail = self.query_one("#job-detail", JobDetail)
        detail.clear()
        
        # Load cached jobs
        await self.load_jobs()
        
        # Update status bar
        await self.update_status()

    async def load_jobs(self, search_query: str = "") -> None:
        """Load jobs from cache."""
        if self.db is None:
            return

        if search_query:
            self.jobs = await self.db.search_jobs(search_query, limit=100)
            self.current_search = search_query
        else:
            self.jobs = await self.db.get_jobs(limit=100)
            self.current_search = ""

        # Update table
        table = self.query_one("#job-table", DataTable)
        table.clear()
        
        for i, job in enumerate(self.jobs, 1):
            salary = f"¥{job.salary_range}" if job.salary_range else "-"
            # Truncate long fields
            title = job.title[:30] + "..." if len(job.title) > 30 else job.title
            company = job.company[:20] + "..." if len(job.company) > 20 else job.company
            location = job.location[:15] + "..." if len(job.location) > 15 else job.location
            source = job.source or "-"
            
            table.add_row(str(i), title, company, salary, location, source)

        await self.update_status()

    async def update_status(self) -> None:
        """Update the status bar."""
        if self.db is None:
            return
            
        stats = await self.db.get_monthly_usage()
        job_count = len(self.jobs)
        
        status = self.query_one("#status-bar", StatusBar)
        status.update_stats(
            stats.requests_used,
            stats.monthly_limit,
            job_count,
            self.current_search,
            self.current_page,
            self.has_more,
            self.current_platform,
            self.current_location,
            self.filters,
        )

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the job table."""
        if event.row_key is not None:
            row_index = event.cursor_row
            if 0 <= row_index < len(self.jobs):
                self.selected_job = self.jobs[row_index]
                detail = self.query_one("#job-detail", JobDetail)
                detail.show_job(self.selected_job)
                self.detail_visible = True

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        command = event.value.strip()
        event.input.value = ""
        
        if not command:
            return
            
        self.process_command(command)
        
        # Return focus to table
        table = self.query_one("#job-table", DataTable)
        table.focus()

    def process_command(self, command: str) -> None:
        """Process a command string."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("q", "quit", "exit"):
            self.exit()
        elif cmd == "search":
            if args:
                # do_search is a @work decorated method, call it directly
                self.do_search(args)
            else:
                self.notify("Usage: search <query>", severity="warning")
        elif cmd == "list":
            self.run_worker(self._load_jobs_worker())
        elif cmd == "refresh":
            # do_refresh is a @work decorated method, call it directly
            self.do_refresh(args or "软件工程师")
        elif cmd == "stats":
            self.run_worker(self._show_stats_worker())
        elif cmd in ("open", "o"):
            self.action_open_job()
        elif cmd == "show":
            if args:
                try:
                    idx = int(args) - 1
                    if 0 <= idx < len(self.jobs):
                        self.selected_job = self.jobs[idx]
                        detail = self.query_one("#job-detail", JobDetail)
                        detail.show_job(self.selected_job)
                        # Also select in table
                        table = self.query_one("#job-table", DataTable)
                        table.move_cursor(row=idx)
                except ValueError:
                    self.notify("Usage: show <number>", severity="warning")
        elif cmd == "help":
            self.action_show_help()
        elif cmd in ("more", "next", "n"):
            self.action_load_more()
        elif cmd in ("platform", "p"):
            if args:
                self._set_platform(args)
            else:
                self.notify(f"Current platform: {self.current_platform}. Usage: platform <zhaopin|linkedin|all>", severity="information")
        elif cmd in ("location", "loc", "l"):
            if args:
                self._set_location(args)
            else:
                self.notify(f"Current location: {self.current_location}. Usage: location <city>", severity="information")
        elif cmd == "filter":
            self._handle_filter_command(args)
        else:
            self.notify(f"Unknown command: {cmd}. Type 'help' for commands.", severity="warning")

    def _set_platform(self, platform: str) -> None:
        """Set the current platform."""
        platform = platform.lower().strip()
        valid_platforms = ["zhaopin", "linkedin", "all"]
        if platform in valid_platforms:
            self.current_platform = platform
            self.run_worker(self._update_status_worker())
            self.notify(f"Platform set to: {platform}")
        else:
            self.notify(f"Invalid platform. Use: {', '.join(valid_platforms)}", severity="warning")

    def _set_location(self, location: str) -> None:
        """Set the current location."""
        self.current_location = location.strip()
        self.run_worker(self._update_status_worker())
        self.notify(f"Location set to: {self.current_location}")

    def _handle_filter_command(self, args: str) -> None:
        """Handle filter commands."""
        if not args:
            if self.filters:
                filter_str = ", ".join(f"{k}={v}" for k, v in self.filters.items())
                self.notify(f"Current filters: {filter_str}")
            else:
                self.notify("No filters set. Usage: filter tech=python, filter salary=20, filter exp=3-5, filter clear")
            return
        
        args_lower = args.lower().strip()
        
        if args_lower == "clear":
            self.filters = {}
            self.run_worker(self._apply_filters_worker())
            self.notify("Filters cleared")
            return
        
        # Parse filter: tech=python, salary=20, exp=3-5
        if "=" in args:
            key, value = args.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            
            if key == "tech":
                self.filters["tech"] = value
                self.notify(f"Filter tech={value} applied")
            elif key in ("salary", "salary_min", "sal"):
                try:
                    self.filters["salary_min"] = int(value)
                    self.notify(f"Filter salary>={value}k applied")
                except ValueError:
                    self.notify("Salary must be a number (e.g., filter salary=20)", severity="warning")
                    return
            elif key in ("exp", "experience"):
                self.filters["exp"] = value
                self.notify(f"Filter exp={value} applied")
            else:
                self.notify(f"Unknown filter: {key}. Use: tech, salary, exp", severity="warning")
                return
            
            self.run_worker(self._apply_filters_worker())
        else:
            self.notify("Usage: filter tech=python, filter salary=20, filter exp=3-5, filter clear", severity="warning")

    async def _update_status_worker(self) -> None:
        """Worker for updating status bar."""
        await self.update_status()

    async def _apply_filters_worker(self) -> None:
        """Worker for applying filters and refreshing display."""
        await self._apply_filters()

    async def _apply_filters(self) -> None:
        """Apply current filters to the job list and refresh display."""
        if self.db is None:
            return
        
        # Re-fetch from cache and apply filters
        if self.current_search:
            all_jobs = await self.db.search_jobs(self.current_search, limit=500)
        else:
            all_jobs = await self.db.get_jobs(limit=500)
        
        # Apply filters
        self.jobs = filter_jobs(
            all_jobs,
            tech=self.filters.get("tech"),
            salary_min=self.filters.get("salary_min"),
            exp=self.filters.get("exp"),
        )
        
        await self.refresh_table()
        await self.update_status()

    @work(exclusive=True)
    async def do_search(self, query: str, page: int = 1, append: bool = False) -> None:
        """Perform a search (may fetch from API).
        
        Args:
            query: Search query
            page: Page number to fetch
            append: If True, append to existing results instead of replacing
        """
        platform = self.current_platform
        location = self.current_location
        
        if page == 1:
            self.notify(f"Searching '{query}' on {platform} @ {location}...")
        else:
            self.notify(f"Loading page {page}...")
        
        if self.db is None:
            return

        # First try cache (only for page 1)
        if page == 1 and not append:
            # Search cache with platform filter if not "all"
            source_filter = None if platform == "all" else platform
            cached = await self.db.search_jobs(query, source=source_filter, limit=500)
            
            if cached:
                # Apply filters
                filtered = filter_jobs(
                    cached,
                    tech=self.filters.get("tech"),
                    salary_min=self.filters.get("salary_min"),
                    exp=self.filters.get("exp"),
                )
                self.jobs = filtered
                self.current_search = query
                self.current_page = 1
                self.has_more = True  # Assume there's more when showing cache
                await self.refresh_table()
                filter_str = f" ({len(filtered)}/{len(cached)} after filters)" if self.filters else ""
                self.notify(f"Found {len(cached)} cached jobs for '{query}'{filter_str}. Press 'n' to fetch more from API.")
                await self.update_status()
                return

        # Fetch from API
        if page == 1:
            self.notify(f"Fetching from {platform} API...")
        
        try:
            settings = get_settings()
            if not settings.bright_data_api_token:
                self.notify("API token not configured", severity="error")
                return

            all_jobs: list[JobPosting] = []
            
            # Determine which scrapers to use
            if platform == "all":
                scrapers_to_use = ["zhaopin", "linkedin"]
            else:
                scrapers_to_use = [platform]
            
            for scraper_name in scrapers_to_use:
                try:
                    mcp = BrightDataMCP()
                    
                    if scraper_name == "zhaopin":
                        scraper = ZhaopinScraper(mcp)
                        result = await scraper.search(query, location, page=page)
                    elif scraper_name == "linkedin":
                        scraper = LinkedInScraper(mcp)
                        result = await scraper.search(query, location, page=page, filter_location=True)
                    else:
                        continue
                    
                    await self.db.increment_request_count(1)
                    
                    if result.jobs:
                        all_jobs.extend(result.jobs)
                        self.has_more = self.has_more or result.has_more
                    
                except Exception as e:
                    self.notify(f"{scraper_name} error: {e}", severity="warning")
            
            if all_jobs:
                await self.db.save_jobs(all_jobs)
                
                # Apply filters
                filtered = filter_jobs(
                    all_jobs,
                    tech=self.filters.get("tech"),
                    salary_min=self.filters.get("salary_min"),
                    exp=self.filters.get("exp"),
                )
                
                if append:
                    self.jobs.extend(filtered)
                else:
                    self.jobs = filtered
                    
                self.current_search = query
                self.current_page = page
                await self.refresh_table()
                
                filter_str = f" ({len(filtered)}/{len(all_jobs)} after filters)" if self.filters else ""
                if append:
                    self.notify(f"Loaded {len(all_jobs)} more jobs{filter_str} (total: {len(self.jobs)})")
                else:
                    self.notify(f"Found {len(all_jobs)} jobs{filter_str} for '{query}'")
            else:
                self.has_more = False
                if page > 1:
                    self.notify("No more jobs found", severity="warning")
                else:
                    self.notify(f"No jobs found for '{query}'", severity="warning")
                
        except Exception as e:
            self.notify(f"Search failed: {e}", severity="error")

        await self.update_status()

    @work(exclusive=True)
    async def do_refresh(self, query: str) -> None:
        """Refresh jobs from API."""
        platform = self.current_platform
        location = self.current_location
        
        self.notify(f"Refreshing from {platform} @ {location} (query: '{query}')...")
        
        if self.db is None:
            return

        try:
            settings = get_settings()
            if not settings.bright_data_api_token:
                self.notify("API token not configured", severity="error")
                return
            
            all_jobs: list[JobPosting] = []
            
            # Determine which scrapers to use
            if platform == "all":
                scrapers_to_use = ["zhaopin", "linkedin"]
            else:
                scrapers_to_use = [platform]
            
            for scraper_name in scrapers_to_use:
                try:
                    mcp = BrightDataMCP()
                    
                    if scraper_name == "zhaopin":
                        scraper = ZhaopinScraper(mcp)
                        result = await scraper.search(query, location)
                    elif scraper_name == "linkedin":
                        scraper = LinkedInScraper(mcp)
                        result = await scraper.search(query, location, filter_location=True)
                    else:
                        continue
                    
                    await self.db.increment_request_count(1)
                    await self.db.set_last_refresh(scraper_name)
                    
                    if result.jobs:
                        all_jobs.extend(result.jobs)
                        
                except Exception as e:
                    self.notify(f"{scraper_name} error: {e}", severity="warning")
            
            if all_jobs:
                await self.db.save_jobs(all_jobs)
                
                # Reload job list with filters
                if self.current_search:
                    all_cached = await self.db.search_jobs(self.current_search, limit=500)
                else:
                    all_cached = await self.db.get_jobs(limit=500)
                
                self.jobs = filter_jobs(
                    all_cached,
                    tech=self.filters.get("tech"),
                    salary_min=self.filters.get("salary_min"),
                    exp=self.filters.get("exp"),
                )
                await self.refresh_table()
                self.notify(f"Refreshed: {len(all_jobs)} jobs fetched from {platform}")
            else:
                self.notify("No jobs returned from refresh", severity="warning")
                
        except Exception as e:
            self.notify(f"Refresh failed: {e}", severity="error")

        await self.update_status()

    async def _show_stats_worker(self) -> None:
        """Worker for showing statistics."""
        await self.show_stats()

    async def _load_jobs_worker(self) -> None:
        """Worker for loading jobs."""
        await self.load_jobs()
        self.notify(f"Loaded {len(self.jobs)} jobs from cache")

    async def show_stats(self) -> None:
        """Show statistics notification."""
        if self.db is None:
            return
            
        stats = await self.db.get_monthly_usage()
        job_count = await self.db.get_job_count()
        
        self.notify(
            f"API: {stats.requests_used}/{stats.monthly_limit} | "
            f"Cached jobs: {job_count} | "
            f"Remaining: {stats.requests_remaining}",
            timeout=5,
        )

    async def refresh_table(self) -> None:
        """Refresh the jobs table display."""
        table = self.query_one("#job-table", DataTable)
        table.clear()
        
        for i, job in enumerate(self.jobs, 1):
            salary = f"¥{job.salary_range}" if job.salary_range else "-"
            title = job.title[:30] + "..." if len(job.title) > 30 else job.title
            company = job.company[:20] + "..." if len(job.company) > 20 else job.company
            location = job.location[:15] + "..." if len(job.location) > 15 else job.location
            source = job.source or "-"
            
            table.add_row(str(i), title, company, salary, location, source)

    def action_cursor_down(self) -> None:
        """Move cursor down in table."""
        table = self.query_one("#job-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in table."""
        table = self.query_one("#job-table", DataTable)
        table.action_cursor_up()

    def action_select_job(self) -> None:
        """Select current job or open in browser if detail visible."""
        if self.detail_visible and self.selected_job:
            self.action_open_job()
        else:
            table = self.query_one("#job-table", DataTable)
            row_index = table.cursor_row
            if 0 <= row_index < len(self.jobs):
                self.selected_job = self.jobs[row_index]
                detail = self.query_one("#job-detail", JobDetail)
                detail.show_job(self.selected_job)
                self.detail_visible = True

    def action_open_job(self) -> None:
        """Open selected job in browser."""
        if self.selected_job:
            webbrowser.open(self.selected_job.url)
            self.notify(f"Opening {self.selected_job.url}")

    def action_clear_detail(self) -> None:
        """Clear the detail panel."""
        detail = self.query_one("#job-detail", JobDetail)
        detail.clear()
        self.selected_job = None
        self.detail_visible = False

    def action_focus_search(self) -> None:
        """Focus the command input for searching."""
        cmd_input = self.query_one("#command-input", CommandInput)
        cmd_input.value = "search "
        cmd_input.focus()

    def action_refresh(self) -> None:
        """Trigger a refresh."""
        # do_refresh is @work decorated, call directly
        self.do_refresh(self.current_search or "软件工程师")

    def action_load_more(self) -> None:
        """Load more results from the next page."""
        if not self.current_search:
            self.notify("No active search. Use '/' to search first.", severity="warning")
            return
            
        if not self.has_more:
            self.notify("No more results available.", severity="warning")
            return
            
        next_page = self.current_page + 1
        # do_search is @work decorated, call directly
        self.do_search(self.current_search, page=next_page, append=True)

    def action_show_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpModal())


def run_tui() -> None:
    """Run the TUI application."""
    app = JobsApp()
    app.run()


if __name__ == "__main__":
    run_tui()
