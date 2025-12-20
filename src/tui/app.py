"""Main TUI application for jobs-cli."""

import asyncio
import webbrowser
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
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


# =============================================================================
# Modal Screens
# =============================================================================

class SearchModal(ModalScreen[Optional[str]]):
    """Modal for entering search query."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    SearchModal {
        align: center middle;
    }

    #search-container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #search-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
        border-bottom: solid $primary;
        margin-bottom: 1;
    }

    #search-input {
        margin: 1 0;
    }

    #search-hint {
        color: $text-muted;
        margin-top: 1;
    }

    #search-footer {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        border-top: solid $primary;
        margin-top: 1;
    }
    """

    def __init__(self, last_search: str = "") -> None:
        super().__init__()
        self.last_search = last_search

    def compose(self) -> ComposeResult:
        with Container(id="search-container"):
            yield Static("Search Jobs", id="search-title")
            yield Input(placeholder="Enter search query...", id="search-input")
            if self.last_search:
                yield Static(f"[dim]Last: \"{self.last_search}\"[/dim]", id="search-hint")
            yield Static("[Enter] Search    [Esc] Cancel", id="search-footer")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if query:
            self.dismiss(query)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class PlatformModal(ModalScreen[Optional[str]]):
    """Modal for selecting platform."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("1", "select_zhaopin", "Zhaopin"),
        Binding("2", "select_linkedin", "LinkedIn"),
        Binding("3", "select_all", "All"),
    ]

    CSS = """
    PlatformModal {
        align: center middle;
    }

    #platform-container {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #platform-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
        border-bottom: solid $primary;
        margin-bottom: 1;
    }

    .platform-option {
        padding: 0 2;
        margin: 0 0;
    }

    .platform-option-selected {
        background: $accent;
    }

    #platform-hint {
        color: $text-muted;
        margin-top: 1;
    }

    #platform-footer {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        border-top: solid $primary;
        margin-top: 1;
    }
    """

    def __init__(self, current_platform: str = "zhaopin") -> None:
        super().__init__()
        self.current_platform = current_platform

    def compose(self) -> ComposeResult:
        with Container(id="platform-container"):
            yield Static("Select Platform", id="platform-title")
            yield Static("")
            
            # Show options with current highlighted
            z_mark = "[bold cyan]>[/bold cyan] " if self.current_platform == "zhaopin" else "  "
            l_mark = "[bold cyan]>[/bold cyan] " if self.current_platform == "linkedin" else "  "
            a_mark = "[bold cyan]>[/bold cyan] " if self.current_platform == "all" else "  "
            
            yield Static(f"{z_mark}[yellow][1][/yellow] zhaopin", classes="platform-option")
            yield Static(f"{l_mark}[yellow][2][/yellow] linkedin", classes="platform-option")
            yield Static(f"{a_mark}[yellow][3][/yellow] all (both platforms)", classes="platform-option")
            yield Static("")
            yield Static(f"[dim]Current: {self.current_platform}[/dim]", id="platform-hint")
            yield Static("Press [yellow]1[/yellow]/[yellow]2[/yellow]/[yellow]3[/yellow] or [Esc] Cancel", id="platform-footer")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select_zhaopin(self) -> None:
        self.dismiss("zhaopin")

    def action_select_linkedin(self) -> None:
        self.dismiss("linkedin")

    def action_select_all(self) -> None:
        self.dismiss("all")


class FilterModal(ModalScreen[Optional[dict]]):
    """Modal for setting filters (including location)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    CSS = """
    FilterModal {
        align: center middle;
    }

    #filter-container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #filter-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
        border-bottom: solid $primary;
        margin-bottom: 1;
    }

    .filter-label {
        margin-top: 1;
        color: $text;
    }

    .filter-input {
        margin: 0 0 1 0;
    }

    #filter-error {
        color: $error;
        margin: 1 0;
    }

    #filter-footer {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        border-top: solid $primary;
        margin-top: 1;
    }
    """

    def __init__(self, current_filters: Optional[dict] = None, current_location: str = "Beijing") -> None:
        super().__init__()
        self.current_filters = current_filters or {}
        self.current_location = current_location

    def compose(self) -> ComposeResult:
        with Container(id="filter-container"):
            yield Static("Set Filters", id="filter-title")
            
            yield Static("Location:", classes="filter-label")
            yield Input(
                value=self.current_location,
                placeholder="e.g., Beijing, Shanghai, Shenzhen",
                id="filter-location",
                classes="filter-input",
            )
            
            yield Static("Tech (comma-separated):", classes="filter-label")
            yield Input(
                value=self.current_filters.get("tech", ""),
                placeholder="e.g., python,django,react",
                id="filter-tech",
                classes="filter-input",
            )
            
            yield Static("Min Salary (k):", classes="filter-label")
            yield Input(
                value=str(self.current_filters.get("salary_min", "")) if self.current_filters.get("salary_min") else "",
                placeholder="e.g., 20 (for 20k+)",
                id="filter-salary",
                classes="filter-input",
            )
            
            yield Static("Experience:", classes="filter-label")
            yield Input(
                value=self.current_filters.get("exp", ""),
                placeholder="e.g., 3-5 or 5+",
                id="filter-exp",
                classes="filter-input",
            )
            
            yield Static("", id="filter-error")
            yield Static("[Tab] Next field    [Enter] Apply    [Esc] Cancel", id="filter-footer")

    def on_mount(self) -> None:
        self.query_one("#filter-location", Input).focus()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Validate and apply filters."""
        location = self.query_one("#filter-location", Input).value.strip()
        tech = self.query_one("#filter-tech", Input).value.strip()
        salary_str = self.query_one("#filter-salary", Input).value.strip()
        exp = self.query_one("#filter-exp", Input).value.strip()
        
        # Validate location
        if not location:
            self.query_one("#filter-error", Static).update("[red]Location is required[/red]")
            return
        
        # Validate salary
        salary_min = None
        if salary_str:
            try:
                salary_min = int(salary_str)
                if salary_min < 0:
                    self.query_one("#filter-error", Static).update("[red]Salary must be a positive number[/red]")
                    return
            except ValueError:
                self.query_one("#filter-error", Static).update("[red]Salary must be a positive number[/red]")
                return
        
        # Build result dict (location is separate from filters)
        result = {
            "location": location,
            "filters": {}
        }
        if tech:
            result["filters"]["tech"] = tech
        if salary_min is not None:
            result["filters"]["salary_min"] = salary_min
        if exp:
            result["filters"]["exp"] = exp
        
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen):
    """Modal screen showing keyboard shortcuts."""

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
        width: 60;
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

    .help-section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }

    .help-row {
        padding-left: 2;
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
            yield Static("[yellow]j / Down[/yellow]     Move down in job list", classes="help-row")
            yield Static("[yellow]k / Up[/yellow]       Move up in job list", classes="help-row")
            yield Static("[yellow]Enter[/yellow]        Select job / Open in browser", classes="help-row")
            yield Static("[yellow]Esc[/yellow]          Clear selection / Close modal", classes="help-row")
            
            # Actions section
            yield Static("[bold cyan]Actions[/bold cyan]", classes="help-section-title")
            yield Static("[yellow]s[/yellow]            Search for jobs", classes="help-row")
            yield Static("[yellow]p[/yellow]            Select platform", classes="help-row")
            yield Static("[yellow]f[/yellow]            Set filters (location, tech, salary, exp)", classes="help-row")
            yield Static("[yellow]c[/yellow]            Clear all filters", classes="help-row")
            yield Static("[yellow]r[/yellow]            Refresh from API", classes="help-row")
            yield Static("[yellow]n[/yellow]            Load next page", classes="help-row")
            yield Static("[yellow]o[/yellow]            Open job in browser", classes="help-row")
            yield Static("[yellow]?[/yellow]            Show this help", classes="help-row")
            yield Static("[yellow]q[/yellow]            Quit", classes="help-row")
            
            # Advanced section
            yield Static("[bold cyan]Advanced[/bold cyan]", classes="help-section-title")
            yield Static("[yellow]:[/yellow]            Command mode (vim-like)", classes="help-row")
            
            yield Static("Press [bold]Esc[/bold] or [bold]q[/bold] to close", id="help-footer")


# =============================================================================
# Status Bar and Job Detail
# =============================================================================

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
        self.loading: bool = False
        self.loading_message: str = ""

    def set_loading(self, loading: bool, message: str = "Loading...") -> None:
        """Set loading state."""
        self.loading = loading
        self.loading_message = message
        self.refresh_display()

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
        self.loading = False  # Clear loading when stats update
        self.refresh_display()

    def refresh_display(self) -> None:
        """Refresh the status bar display."""
        # Show loading indicator if loading
        if self.loading:
            self.update(f"[bold yellow]{self.loading_message}[/bold yellow]")
            return
        
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
        salary = f"[green]{job.salary_range}[/green]" if job.salary_range else "[dim]Not specified[/dim]"
        
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
    """Command input field (hidden by default, shown with ':')."""

    def __init__(self, **kwargs) -> None:
        super().__init__(placeholder=":", **kwargs)


# =============================================================================
# Main Application
# =============================================================================

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
        display: none;
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
        Binding("s", "show_search", "Search"),
        Binding("p", "show_platform", "Platform"),
        Binding("f", "show_filters", "Filters"),
        Binding("c", "clear_filters", "Clear"),
        Binding("colon", "command_mode", ":", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("enter", "select_job", "Select", show=False),
        Binding("escape", "handle_escape", "Esc", show=False),
        Binding("o", "open_job", "Open"),
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
        self.current_platform: str = "zhaopin"
        self.current_location: str = "Beijing"
        self.filters: dict = {}
        self.command_mode_active: bool = False

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

    # =========================================================================
    # Modal Actions
    # =========================================================================

    def action_show_search(self) -> None:
        """Show search modal."""
        self.push_screen(SearchModal(self.current_search), self._on_search_result)

    def action_show_platform(self) -> None:
        """Show platform modal."""
        self.push_screen(PlatformModal(self.current_platform), self._on_platform_result)

    def action_show_filters(self) -> None:
        """Show filters modal (includes location)."""
        self.push_screen(FilterModal(self.filters, self.current_location), self._on_filters_result)

    def action_clear_filters(self) -> None:
        """Clear all filters (keeps location) and re-search."""
        self.filters = {}
        self.notify("Filters cleared")
        if self.current_search:
            self.do_search(self.current_search)
        else:
            self.run_worker(self._update_status_worker())

    def action_command_mode(self) -> None:
        """Show hidden command input (vim-like ':')."""
        cmd_input = self.query_one("#command-input", CommandInput)
        cmd_input.display = True
        cmd_input.value = ""
        cmd_input.focus()
        self.command_mode_active = True

    def action_show_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpModal())

    # =========================================================================
    # Modal Callbacks
    # =========================================================================

    def _on_search_result(self, query: Optional[str]) -> None:
        """Handle search modal result."""
        if query:
            self.do_search(query)

    def _on_platform_result(self, platform: Optional[str]) -> None:
        """Handle platform modal result."""
        if platform:
            self.current_platform = platform
            self.notify(f"Platform set to: {platform}")
            if self.current_search:
                self.do_search(self.current_search)
            else:
                self.run_worker(self._update_status_worker())

    def _on_filters_result(self, result: Optional[dict]) -> None:
        """Handle filters modal result (includes location)."""
        if result is not None:
            # Extract location and filters from result
            self.current_location = result.get("location", self.current_location)
            self.filters = result.get("filters", {})
            
            if self.filters:
                self.notify(f"Filters applied @ {self.current_location}")
            else:
                self.notify(f"Location set to: {self.current_location}")
            
            if self.current_search:
                self.do_search(self.current_search)
            else:
                self.run_worker(self._apply_filters_worker())

    # =========================================================================
    # Navigation Actions
    # =========================================================================

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

    def action_handle_escape(self) -> None:
        """Handle escape key - hide command input or clear detail."""
        cmd_input = self.query_one("#command-input", CommandInput)
        if cmd_input.display:
            cmd_input.display = False
            cmd_input.value = ""
            self.command_mode_active = False
            self.query_one("#job-table", DataTable).focus()
        else:
            # Clear detail panel
            detail = self.query_one("#job-detail", JobDetail)
            detail.clear()
            self.selected_job = None
            self.detail_visible = False

    def action_refresh(self) -> None:
        """Trigger a refresh."""
        self.do_refresh(self.current_search or "software engineer")

    def action_load_more(self) -> None:
        """Load more results from the next page."""
        if not self.current_search:
            self.notify("No active search. Press 's' to search first.", severity="warning")
            return
            
        if not self.has_more:
            self.notify("No more results available.", severity="warning")
            return
            
        next_page = self.current_page + 1
        self.do_search(self.current_search, page=next_page, append=True)

    # =========================================================================
    # Event Handlers
    # =========================================================================

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

    @on(Input.Submitted, "#command-input")
    def on_command_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input submission (only from #command-input)."""
        command = event.value.strip()
        event.input.value = ""
        event.input.display = False
        self.command_mode_active = False
        
        if command:
            self.process_command(command)
        
        # Return focus to table
        self.query_one("#job-table", DataTable).focus()

    # =========================================================================
    # Command Processing (for vim-like ':' mode)
    # =========================================================================

    def process_command(self, command: str) -> None:
        """Process a command string (vim-like command mode)."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("q", "quit", "exit"):
            self.exit()
        elif cmd == "search":
            if args:
                self.do_search(args)
            else:
                self.notify("Usage: search <query>", severity="warning")
        elif cmd == "list":
            self.run_worker(self._load_jobs_worker())
        elif cmd == "refresh":
            self.do_refresh(args or self.current_search or "software engineer")
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
                        table = self.query_one("#job-table", DataTable)
                        table.move_cursor(row=idx)
                except ValueError:
                    self.notify("Usage: show <number>", severity="warning")
        elif cmd == "help":
            self.action_show_help()
        elif cmd in ("more", "next"):
            self.action_load_more()
        elif cmd in ("platform", "p"):
            if args and args.lower() in ["zhaopin", "linkedin", "all"]:
                self._on_platform_result(args.lower())
            else:
                self.notify(f"Current: {self.current_platform}. Usage: platform <zhaopin|linkedin|all>")
        elif cmd in ("location", "loc"):
            if args:
                self.current_location = args.strip()
                self.notify(f"Location set to: {self.current_location}")
                if self.current_search:
                    self.do_search(self.current_search)
                else:
                    self.run_worker(self._update_status_worker())
            else:
                self.notify(f"Current: {self.current_location}. Usage: location <city>")
        elif cmd == "filter":
            if args == "clear":
                self.action_clear_filters()
            else:
                self.notify("Use 'f' key to set filters, or 'filter clear' to clear")
        else:
            self.notify(f"Unknown command: {cmd}. Press '?' for help.", severity="warning")

    # =========================================================================
    # Data Loading and Workers
    # =========================================================================

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
            salary = f"{job.salary_range}" if job.salary_range else "-"
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

    async def refresh_table(self) -> None:
        """Refresh the jobs table display."""
        table = self.query_one("#job-table", DataTable)
        table.clear()
        
        for i, job in enumerate(self.jobs, 1):
            salary = f"{job.salary_range}" if job.salary_range else "-"
            title = job.title[:30] + "..." if len(job.title) > 30 else job.title
            company = job.company[:20] + "..." if len(job.company) > 20 else job.company
            location = job.location[:15] + "..." if len(job.location) > 15 else job.location
            source = job.source or "-"
            
            table.add_row(str(i), title, company, salary, location, source)

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
        
        if self.current_search:
            all_jobs = await self.db.search_jobs(self.current_search, limit=500)
        else:
            all_jobs = await self.db.get_jobs(limit=500)
        
        self.jobs = filter_jobs(
            all_jobs,
            tech=self.filters.get("tech"),
            salary_min=self.filters.get("salary_min"),
            exp=self.filters.get("exp"),
        )
        
        await self.refresh_table()
        await self.update_status()

    async def _show_stats_worker(self) -> None:
        """Worker for showing statistics."""
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

    async def _load_jobs_worker(self) -> None:
        """Worker for loading jobs."""
        await self.load_jobs()
        self.notify(f"Loaded {len(self.jobs)} jobs from cache")

    # =========================================================================
    # Search and Refresh Workers
    # =========================================================================

    @work(exclusive=True)
    async def do_search(self, query: str, page: int = 1, append: bool = False) -> None:
        """Perform a search (may fetch from API)."""
        platform = self.current_platform
        location = self.current_location
        
        # Show loading indicator
        status = self.query_one("#status-bar", StatusBar)
        if page == 1:
            status.set_loading(True, f"Searching '{query}' on {platform} @ {location}...")
        else:
            status.set_loading(True, f"Loading page {page}...")
        
        if self.db is None:
            status.set_loading(False)
            return

        # First try cache (only for page 1)
        if page == 1 and not append:
            source_filter = None if platform == "all" else platform
            cached = await self.db.search_jobs(query, source=source_filter, limit=500)
            
            if cached:
                filtered = filter_jobs(
                    cached,
                    tech=self.filters.get("tech"),
                    salary_min=self.filters.get("salary_min"),
                    exp=self.filters.get("exp"),
                )
                self.jobs = filtered
                self.current_search = query
                self.current_page = 1
                self.has_more = True
                await self.refresh_table()
                filter_str = f" ({len(filtered)}/{len(cached)} after filters)" if self.filters else ""
                self.notify(f"Found {len(cached)} cached jobs{filter_str}. Press 'n' for more.")
                await self.update_status()
                return

        # Fetch from API
        status.set_loading(True, f"Fetching from {platform} API...")
        
        try:
            settings = get_settings()
            if not settings.bright_data_api_token:
                self.notify("API token not configured", severity="error")
                return

            all_jobs: list[JobPosting] = []
            
            if platform == "all":
                scrapers_to_use = ["zhaopin", "linkedin"]
            else:
                scrapers_to_use = [platform]
            
            for scraper_name in scrapers_to_use:
                try:
                    status.set_loading(True, f"Fetching from {scraper_name}...")
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
                    self.notify(f"Found {len(all_jobs)} jobs{filter_str}")
            else:
                self.has_more = False
                if page > 1:
                    self.notify("No more jobs found", severity="warning")
                else:
                    self.notify(f"No jobs found for '{query}'", severity="warning")
                
        except Exception as e:
            self.notify(f"Search failed: {e}", severity="error")
        finally:
            # Always clear loading state and update status
            status.set_loading(False)

        await self.update_status()

    @work(exclusive=True)
    async def do_refresh(self, query: str) -> None:
        """Refresh jobs from API."""
        platform = self.current_platform
        location = self.current_location
        
        # Show loading indicator
        status = self.query_one("#status-bar", StatusBar)
        status.set_loading(True, f"Refreshing from {platform} @ {location}...")
        
        if self.db is None:
            status.set_loading(False)
            return

        try:
            settings = get_settings()
            if not settings.bright_data_api_token:
                self.notify("API token not configured", severity="error")
                status.set_loading(False)
                return
            
            all_jobs: list[JobPosting] = []
            
            if platform == "all":
                scrapers_to_use = ["zhaopin", "linkedin"]
            else:
                scrapers_to_use = [platform]
            
            for scraper_name in scrapers_to_use:
                try:
                    status.set_loading(True, f"Fetching from {scraper_name}...")
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
                self.notify(f"Refreshed: {len(all_jobs)} jobs fetched")
            else:
                self.notify("No jobs returned from refresh", severity="warning")
                
        except Exception as e:
            self.notify(f"Refresh failed: {e}", severity="error")
        finally:
            # Always clear loading state
            status.set_loading(False)

        await self.update_status()


def run_tui() -> None:
    """Run the TUI application."""
    app = JobsApp()
    app.run()


if __name__ == "__main__":
    run_tui()
