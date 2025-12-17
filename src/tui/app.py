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
from ..utils.parser import parse_salary_min


class StatusBar(Static):
    """Status bar showing API usage and cache stats."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.api_usage = "0/5000"
        self.job_count = 0
        self.last_search = ""
        self.current_page = 1
        self.has_more = False

    def update_stats(
        self,
        api_used: int,
        api_limit: int,
        job_count: int,
        last_search: str = "",
        current_page: int = 1,
        has_more: bool = False,
    ) -> None:
        """Update the status bar with new stats."""
        self.api_usage = f"{api_used}/{api_limit}"
        self.job_count = job_count
        self.last_search = last_search
        self.current_page = current_page
        self.has_more = has_more
        self.refresh_display()

    def refresh_display(self) -> None:
        """Refresh the status bar display."""
        search_info = f" | Search: '{self.last_search}'" if self.last_search else ""
        page_info = f" | Page {self.current_page}" if self.last_search else ""
        more_info = " [n=more]" if self.has_more else ""
        self.update(f"Jobs: {self.job_count} | API: {self.api_usage}{search_info}{page_info}{more_info}")


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
            
            yield Static("Press [bold]Esc[/bold], [bold]q[/bold], or [bold]?[/bold] to close", id="help-footer")


class JobsApp(App):
    """Interactive TUI for browsing jobs."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-columns: 2fr 1fr;
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
        table.add_columns("#", "Title", "Company", "Salary", "Location")
        
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
            
            table.add_row(str(i), title, company, salary, location)

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
        else:
            self.notify(f"Unknown command: {cmd}. Type 'help' for commands.", severity="warning")

    @work(exclusive=True)
    async def do_search(self, query: str, page: int = 1, append: bool = False) -> None:
        """Perform a search (may fetch from API).
        
        Args:
            query: Search query
            page: Page number to fetch
            append: If True, append to existing results instead of replacing
        """
        if page == 1:
            self.notify(f"Searching for '{query}'...")
        else:
            self.notify(f"Loading page {page}...")
        
        if self.db is None:
            return

        # First try cache (only for page 1)
        if page == 1 and not append:
            cached = await self.db.search_jobs(query, limit=100)
            
            if cached:
                self.jobs = cached
                self.current_search = query
                self.current_page = 1
                self.has_more = True  # Assume there's more when showing cache
                await self.refresh_table()
                self.notify(f"Found {len(cached)} cached jobs for '{query}'. Press 'n' to fetch more from API.")
                await self.update_status()
                return

        # Fetch from API
        if page == 1:
            self.notify("Fetching from API...")
        
        try:
            settings = get_settings()
            if not settings.bright_data_api_token:
                self.notify("API token not configured", severity="error")
                return
                
            mcp = BrightDataMCP()
            scraper = ZhaopinScraper(mcp)
            result = await scraper.search(query, "Beijing", page=page)
            
            if result.jobs:
                await self.db.save_jobs(result.jobs)
                await self.db.increment_request_count(1)
                
                if append:
                    self.jobs.extend(result.jobs)
                else:
                    self.jobs = result.jobs
                    
                self.current_search = query
                self.current_page = page
                self.has_more = result.has_more
                await self.refresh_table()
                
                if append:
                    self.notify(f"Loaded {len(result.jobs)} more jobs (total: {len(self.jobs)})")
                else:
                    self.notify(f"Found {len(result.jobs)} jobs for '{query}'")
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
        self.notify(f"Refreshing jobs (query: '{query}')...")
        
        if self.db is None:
            return

        try:
            settings = get_settings()
            if not settings.bright_data_api_token:
                self.notify("API token not configured", severity="error")
                return
                
            mcp = BrightDataMCP()
            scraper = ZhaopinScraper(mcp)
            result = await scraper.search(query, "Beijing")
            
            if result.jobs:
                await self.db.save_jobs(result.jobs)
                await self.db.increment_request_count(1)
                await self.db.set_last_refresh("zhaopin")
                
                # Reload job list
                await self.load_jobs(self.current_search)
                self.notify(f"Refreshed: {len(result.jobs)} jobs fetched")
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
            
            table.add_row(str(i), title, company, salary, location)

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
        self.run_worker(self.do_refresh(self.current_search or "软件工程师"))

    def action_load_more(self) -> None:
        """Load more results from the next page."""
        if not self.current_search:
            self.notify("No active search. Use '/' to search first.", severity="warning")
            return
            
        if not self.has_more:
            self.notify("No more results available.", severity="warning")
            return
            
        next_page = self.current_page + 1
        self.run_worker(self.do_search(self.current_search, page=next_page, append=True))

    def action_show_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpModal())


def run_tui() -> None:
    """Run the TUI application."""
    app = JobsApp()
    app.run()


if __name__ == "__main__":
    run_tui()
