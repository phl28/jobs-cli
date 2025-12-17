# Beijing Jobs CLI - Implementation Tasks

## Overview
Python CLI to aggregate Beijing software engineering jobs from Chinese platforms (BOSS Zhipin, Zhaopin, 51job, Liepin) using **Bright Data MCP** for web scraping, displayed with Rich.

**CLI Command**: `jobs-cli`

---

## Bright Data MCP - Architecture

### Free Tier (5,000 requests/month)
The free tier provides these MCP tools:
- `search_engine` - Web search with AI-optimized results
- `scrape_as_markdown` - Convert any webpage to **clean markdown**

### How MCP Works
MCP (Model Context Protocol) uses **SSE (Server-Sent Events)** for communication, not regular HTTP REST APIs. You connect to the MCP server and call "tools" through the protocol.

```
┌─────────────────────────────────────────────────────────────┐
│                    Architecture                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  jobs-cli (Python)                                          │
│       │                                                      │
│       ▼                                                      │
│  MCP Client (mcp library)                                   │
│       │                                                      │
│       │ SSE Connection                                       │
│       ▼                                                      │
│  Bright Data MCP Server (https://mcp.brightdata.com/sse)    │
│       │                                                      │
│       │ Tools: search_engine, scrape_as_markdown            │
│       ▼                                                      │
│  Returns: Clean Markdown (not HTML!)                        │
│       │                                                      │
│       ▼                                                      │
│  Parse markdown → Extract job data → Cache in SQLite        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Key Dependencies
```bash
uv add mcp httpx rich typer pydantic pydantic-settings aiosqlite
```

Note: `mcp` is the official MCP Python SDK from Anthropic.

### Setup Instructions

#### Step 1: Create Bright Data Account
1. Go to https://brightdata.com/ai/mcp-server
2. Click "Start Free"
3. Create account (email or Google/GitHub OAuth)
4. Verify email

#### Step 2: Get API Token
1. Log into Bright Data dashboard: https://brightdata.com/cp
2. Go to Settings → API tokens (or check welcome email)
3. Copy your API token
4. Save it for `.env` file

#### Step 3: Configure Environment
Create `.env` file:
```bash
BRIGHT_DATA_API_TOKEN=your_api_token_here
```

#### Step 4: Test (Optional)
Test in playground first: https://brightdata.com/ai/playground-chat
- Try scraping a Chinese job site URL
- See what markdown output looks like

---

## Sprint 1: Foundation (Days 1-3) - COMPLETED

### 1.1 Project Setup
- [x] Add dependencies via uv:
  ```bash
  uv add mcp httpx rich typer pydantic pydantic-settings aiosqlite
  ```
- [x] Add CLI script entry to `pyproject.toml`:
  ```toml
  [project.scripts]
  jobs-cli = "src.main:main"
  ```
- [x] Create directory structure:
  ```
  src/
  ├── __init__.py
  ├── main.py
  ├── config.py
  ├── models.py
  ├── scrapers/
  │   └── __init__.py
  ├── client/
  │   └── __init__.py
  ├── cache/
  │   └── __init__.py
  ├── display/
  │   └── __init__.py
  └── utils/
      └── __init__.py
  ```
- [x] Create `.env.example` with Bright Data API token
- [x] Create `.gitignore` (Python, .env, cache, __pycache__)

### 1.2 Data Models (`src/models.py`)
- [x] `JobPosting` - id, title, company, location, salary_range, experience, education, description, requirements, tags, posted_date, url, source, fetched_at
- [x] `SearchQuery` - query, location, salary_min, platforms, limit
- [x] `ScraperResult` - jobs list, total_count, page, has_more
- [x] `RequestStats` - month, requests_used, monthly_limit

### 1.3 Configuration (`src/config.py`)
- [x] `Settings` class (pydantic-settings) - API token, DB path, cache TTL, enabled scrapers
- [x] Load from env vars + .env file
- [x] Validation for required fields

### 1.4 MCP Client (`src/client/mcp_client.py`)
- [x] `BrightDataMCP` class using official `mcp` SDK
- [x] Connect via SSE to `https://mcp.brightdata.com/sse?token=TOKEN`
- [x] `scrape_as_markdown(url)` - calls `scrape_as_markdown` tool
- [x] `search_engine(query)` - calls `search_engine` tool
- [x] `list_available_tools()` - list tools for verification
- [x] `test_connection()` - verify connectivity

### 1.5 SQLite Cache (`src/cache/database.py`)
- [x] Initialize DB with tables: jobs, request_tracker, cache_metadata
- [x] CRUD: save_jobs(), get_jobs(), search_jobs(), delete_old_jobs()
- [x] Request tracking: increment_count(), get_monthly_usage()
- [x] Cache checks: is_cache_stale(), get_last_refresh()

### 1.6 Rich Display (`src/display/ui.py`)
- [x] `display_jobs_table()` - search results table
- [x] `display_job_detail()` - single job panel view
- [x] `display_stats()` - request usage, cache stats
- [x] Formatters: salary, relative dates, tags
- [x] Error/success/warning message helpers

### 1.7 Basic CLI (`src/main.py`)
- [x] Typer app setup with commands: search, list, show, stats, config, test-connection
- [x] Global options support
- [x] Async command execution

---

## Sprint 2: First Scraper - BOSS Zhipin (Days 4-6)

### 2.1 Base Scraper (`src/scrapers/base.py`)
- [ ] `BaseScraper` ABC with: search(), get_detail(), parse_markdown()
- [ ] Common utilities: markdown parsing, text extraction with regex

### 2.2 BOSS Zhipin Scraper (`src/scrapers/boss_zhipin.py`)
- [ ] Research BOSS Zhipin URLs and page structure
- [ ] Build search URL with query params
- [ ] Parse markdown response to extract:
  - Job title
  - Company name
  - Salary range
  - Location
  - Tags/tech stack
  - Job URL
- [ ] Parse detail page markdown for:
  - Full description
  - Requirements
  - Posted date
- [ ] Handle pagination (if possible via search URL params)
- [ ] Extract unique job ID from URL

### 2.3 Caching Integration
- [ ] Cache-first: return cached if < 24h old
- [ ] Smart refresh: first page daily, full refresh weekly
- [ ] Dedupe by job URL

### 2.4 `jobs-cli search` Command
- [ ] Args: query (positional)
- [ ] Options: --location/-l, --salary-min/-s, --platform/-p, --limit/-n, --no-cache
- [ ] Display results in Rich table
- [ ] Show request usage in footer

---

## Sprint 3: Additional Scrapers (Days 7-10)

### 3.1 Zhaopin Scraper (`src/scrapers/zhaopin.py`) - COMPLETED
- [x] Research page structure
- [x] Implement search + detail parsing from markdown
- [x] Handle pagination
- [x] Extract: title, company, salary, location, experience, education, tags

### 3.2 51job Scraper (`src/scrapers/job51.py`)
- [ ] Research page structure (site may require different approach)
- [ ] Implement search + detail parsing from markdown
- [ ] Handle pagination

### 3.3 Liepin Scraper (`src/scrapers/liepin.py`)
- [ ] Research page structure
- [ ] Implement search + detail parsing from markdown
- [ ] Handle pagination

### 3.4 Scraper Registry (`src/scrapers/__init__.py`)
- [ ] Factory to get scrapers by name
- [ ] Enable/disable via config
- [ ] Run scrapers in parallel

### 3.5 Data Normalization
- [ ] Normalize salary formats (e.g., "20k-35k" standard)
- [ ] Normalize locations
- [ ] Normalize dates
- [ ] Map platform tags to common tags

---

## Sprint 4: Enhanced Features (Days 11-14)

### 4.1 `jobs-cli list` - COMPLETED
- [x] --sort-by (date, salary, company)
- [x] --limit, --source
- [x] Filtering: --tech, --salary-min, --exp

### 4.2 `jobs-cli show <id>` - COMPLETED
- [x] Rich panel with full job details
- [x] --open to launch URL in browser

### 4.3 `jobs-cli refresh` - COMPLETED
- [x] --platform <name> option
- [x] --query and --location options
- [x] Progress bar, report jobs found

### 4.4 `jobs-cli stats` - COMPLETED
- [x] Request usage (used/5000)
- [x] Cache stats (total jobs, per platform)
- [x] Last refresh times

### 4.5 `jobs-cli config` - COMPLETED
- [x] `config --show` - display config

### 4.6 Filtering - COMPLETED
- [x] --tech python,django (filter by tags)
- [x] --salary-min 20 (minimum salary in k)
- [x] --exp 3-5 (experience years filter)

### 4.7 `jobs-cli export` - COMPLETED
- [x] --format json/csv (auto-detected from filename)
- [x] Apply same filters as list (--tech, --salary-min, --exp, --source)

---

## Sprint 5: Polish (Days 15-16) - COMPLETED

### 5.1 Error Handling - COMPLETED
- [x] MCP connection errors -> retry with exponential backoff (3 retries)
- [x] Tool call failures -> fallback to cached data
- [x] Monthly limit reached -> warning at 80%, cache-only mode at 100%
- [x] Added `clear-cache` command to manage old jobs

### 5.2 UX Improvements - COMPLETED
- [x] Progress spinners for scraping operations
- [x] Improved help text with examples
- [x] --verbose / --quiet modes on search command
- [x] Colorful error/warning/success/info messages

### 5.3 Documentation
- [ ] README: installation, usage, config guide (TODO)
- [x] Code docstrings

---

## File Structure

```
jobs-cli/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point (Typer)
│   ├── config.py            # Settings management
│   ├── models.py            # Pydantic models
│   ├── scrapers/
│   │   ├── __init__.py      # Registry
│   │   ├── base.py          # BaseScraper ABC
│   │   ├── boss_zhipin.py
│   │   ├── job51.py
│   │   ├── zhaopin.py
│   │   └── liepin.py
│   ├── client/
│   │   ├── __init__.py
│   │   └── mcp_client.py    # Bright Data MCP client (SSE)
│   ├── cache/
│   │   ├── __init__.py
│   │   └── database.py      # SQLite operations
│   ├── display/
│   │   ├── __init__.py
│   │   └── ui.py            # Rich components
│   └── utils/
│       ├── __init__.py
│       └── parser.py        # Markdown parsing helpers
├── .env.example
├── .gitignore
├── config.yaml
├── pyproject.toml
├── README.md
└── TASKS.md
```

---

## MVP Target (End of Sprint 2)
- Working `jobs-cli search` command
- BOSS Zhipin scraper functional
- SQLite caching working
- Rich table display
- Request tracking

---

## Notes
- **Request budget**: 5000/month free tier
  - Estimated: ~40/day budget
  - Search page + detail page = 2 requests per job detail view
  - Be conservative with pagination
- **Priority**: BOSS Zhipin first (largest platform)
- **No tests**: Skipping test suite per user request
- **MCP returns markdown**: Simpler than HTML parsing, use regex/string parsing
- **Run locally**: `uv run jobs-cli search "python developer"`

---

## Code Example: MCP Client Usage

```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def scrape_job_page():
    url = "https://mcp.brightdata.com/sse?token=YOUR_TOKEN"
    
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize connection
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print([t.name for t in tools.tools])
            # Output: ['search_engine', 'scrape_as_markdown', ...]
            
            # Scrape a job page
            result = await session.call_tool(
                "scrape_as_markdown",
                {"url": "https://www.zhipin.com/job_detail/..."}
            )
            
            # Result contains markdown text
            markdown = result.content[0].text
            print(markdown)

asyncio.run(scrape_job_page())
```

---

## Sprint 6: Interactive TUI Mode (Future)

### 6.1 Long-running TUI Application
- [ ] Convert to a long-running TUI app (like opencode/claude-code)
- [ ] Persistent session - no need to restart for each command
- [ ] Command-based interface (not conversational)
- [ ] Real-time updates and status display

### 6.2 TUI Features
- [ ] Command prompt at bottom
- [ ] Job list view with scrolling
- [ ] Job detail view (side panel or full screen)
- [ ] Status bar showing API usage, cache stats
- [ ] Keyboard shortcuts for common actions

### 6.3 Commands in TUI Mode
- [ ] `search <query>` - search and display results
- [ ] `list` - show cached jobs
- [ ] `show <n>` - view job details
- [ ] `open <n>` - open job URL in browser
- [ ] `refresh` - refresh current results
- [ ] `stats` - show statistics
- [ ] `quit` / `q` - exit

### 6.4 Tech Stack for TUI
- [ ] Consider: Textual, rich.live, or prompt_toolkit
- [ ] Async event loop for background updates
- [ ] Vim-style navigation (j/k for up/down)
