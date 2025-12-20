# Jobs CLI

A terminal-based job search tool for software engineering positions in China, with a beautiful TUI (Text User Interface) built with Textual.

## Installation

### Pre-built Binaries (Recommended)

Download the latest release for your platform from [GitHub Releases](https://github.com/phl28/jobs-cli/releases):

- **macOS (Apple Silicon)**: `jobs-cli-darwin-arm64.tar.gz`
- **macOS (Intel)**: `jobs-cli-darwin-amd64.tar.gz`
- **Linux**: `jobs-cli-linux-amd64.tar.gz`
- **Windows**: `jobs-cli-windows-amd64.zip`

```bash
# macOS/Linux
tar -xzf jobs-cli-darwin-arm64.tar.gz
chmod +x jobs-cli-darwin-arm64
./jobs-cli-darwin-arm64 --help
```

### Via Homebrew (macOS)

```bash
brew tap phl28/tap
brew install jobs-cli
```

### From Source (requires Python 3.12+)

```bash
# Clone the repository
git clone https://github.com/phl28/jobs-cli.git
cd jobs-cli

# Install with uv
uv sync

# Run
uv run jobs-cli --help
```

### Via pip/uvx

```bash
# Install from PyPI
pip install jobs-cli
# or
uvx jobs-cli
```

## Quick Start

1. Get a free Bright Data API token from [brightdata.com](https://brightdata.com)
2. Set up your environment:
   ```bash
   cp .env.example .env
   # Edit .env and add your BRIGHT_DATA_API_TOKEN
   ```
3. Launch the TUI:
   ```bash
   jobs-cli tui
   ```

## TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `s` | Search for jobs |
| `p` | Select platform (zhaopin/linkedin/all) |
| `f` | Set filters (location, tech, salary, experience) |
| `c` | Clear all filters |
| `j/k` | Navigate up/down |
| `Enter` | Select job / Open in browser |
| `o` | Open job in browser |
| `n` | Load next page |
| `r` | Refresh from API |
| `?` | Show help |
| `q` | Quit |

## CLI Commands

```bash
# Search for jobs
jobs-cli search "python developer" --location Beijing --platform zhaopin

# List cached jobs
jobs-cli list --limit 20

# Show job details
jobs-cli show 1

# Export to CSV/JSON
jobs-cli export jobs.csv

# View statistics
jobs-cli stats
```

## Building from Source

### Build Standalone Binary

```bash
# Install dev dependencies
uv pip install pyinstaller

# Build binary
uv run pyinstaller jobs-cli.spec

# Binary is at dist/jobs-cli
./dist/jobs-cli --help
```

## Releasing

Releases are automated via GitHub Actions. To create a new release:

```bash
# Tag a new version
git tag v0.1.0
git push origin v0.1.0
```

The workflow will:
1. Build binaries for macOS (arm64, amd64), Linux, and Windows
2. Create a GitHub Release with all binaries
3. Optionally publish to PyPI (if `PYPI_API_TOKEN` secret is configured)

---

# Project Plan

## Project Overview
A Python CLI tool to aggregate software engineering job listings in Beijing from major Chinese job platforms, displayed beautifully in the terminal using Rich. Personal use, leveraging Bright Data's free tier (5,000 requests/month).

## Tech Stack

### Core Technologies
- **Python 3.14**: Latest Python version
- **httpx**: Modern async HTTP client (better than requests)
- **Rich**: Beautiful terminal UI with tables, progress bars, panels
- **Typer**: Modern CLI framework (built on top of Click)
- **Pydantic**: Data validation and settings management
- **BeautifulSoup4**: HTML parsing
- **SQLite**: Local caching and data persistence

### Development Tools
- **uv**: Fast dependency management (replacing Poetry)
- **pytest**: Testing framework
- **ruff**: Fast Python linter and formatter (replacing black)
- **mypy**: Type checking

## Understanding Bright Data + BeautifulSoup

### What Bright Data Does
Bright Data is a **proxy network and web unlocker** service. Here's what you get:

1. **Proxy Network**: Routes your requests through residential IPs
   - Avoids IP bans/blocks
   - Makes your requests look like they come from real users in different locations
   - Rotates IPs automatically

2. **Web Unlocker**: Handles anti-bot protection
   - Solves CAPTCHAs automatically
   - Bypasses anti-scraping measures (DataDome, PerimeterX, etc.)
   - Handles JavaScript rendering if needed
   - Manages cookies and sessions

3. **What You Get Back**: **RAW HTML**
   - Bright Data returns the HTML content of the page
   - It does NOT parse or extract data for you
   - It just makes sure you successfully GET the page

### What BeautifulSoup Does
BeautifulSoup is an **HTML parser**. Here's what it does:

1. **Parses HTML**: Converts raw HTML into a navigable tree structure
2. **Extracts Data**: Finds specific elements (job titles, companies, salaries)
3. **Cleans Data**: Strips whitespace, normalizes text

### How They Work Together

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Scraping Flow                       │
└─────────────────────────────────────────────────────────────────┘

1. Your Code
   └─> httpx.get(url, proxies=bright_data_proxy)
       │
       ├─> Request goes through Bright Data network
       │   └─> Bright Data:
       │       • Routes through residential IP
       │       • Solves any CAPTCHAs
       │       • Handles JavaScript if needed
       │       • Returns HTML content
       │
       └─> response.text (RAW HTML)
           │
           └─> BeautifulSoup(response.text, 'html.parser')
               └─> soup.find('div', class_='job-title')
                   └─> Extracted: "Senior Python Developer"
```

### Concrete Example

```python
import httpx
from bs4 import BeautifulSoup

# Step 1: Use Bright Data to GET the page (bypassing blocks)
async with httpx.AsyncClient(proxies=bright_data_proxies) as client:
    response = await client.get('https://www.zhaopin.com/jobs/...')
    # Bright Data handled: IP rotation, CAPTCHA, anti-bot
    # You receive: raw HTML string
    
# Step 2: Use BeautifulSoup to PARSE the HTML and extract data
soup = BeautifulSoup(response.text, 'html.parser')

# Extract job title
title = soup.find('h1', class_='job-title').text.strip()
# Extract company
company = soup.find('a', class_='company-name').text.strip()
# Extract salary
salary = soup.find('span', class_='salary-range').text.strip()
```

### Do You NEED Both?

**Yes!** They serve completely different purposes:

- **Without Bright Data**: You'd get blocked/banned quickly, hit CAPTCHAs
- **Without BeautifulSoup**: You'd have raw HTML with no way to extract structured data

### Alternative: Bright Data's Web Scraper API

Bright Data also offers pre-built scrapers for popular sites, but:
- ❌ Not available for Chinese job sites (Zhaopin, 51job, etc.)
- ❌ More expensive (counts against your 5,000 requests differently)
- ✅ Would eliminate need for BeautifulSoup IF they supported your sites

Since Chinese job sites aren't in their pre-built scrapers, you need:
1. **Bright Data**: To successfully fetch pages without getting blocked
2. **BeautifulSoup**: To parse the HTML and extract job data

### What's Included in Free Tier

**Bright Data Free Tier (5,000 requests/month):**
- ✅ Residential proxy network
- ✅ Automatic IP rotation
- ✅ CAPTCHA solving
- ✅ Basic anti-bot bypassing
- ✅ Returns raw HTML
- ❌ Does NOT parse/extract data for you
- ❌ Does NOT include pre-built scrapers for Chinese job sites

### Summary

```
┌──────────────────────────────────────────────────────────────┐
│  Bright Data = "Get me past the bouncer and into the club"  │
│  BeautifulSoup = "Find the person I'm looking for inside"   │
└──────────────────────────────────────────────────────────────┘
```

**Your stack:**
- httpx: Makes HTTP requests
- Bright Data: Ensures requests succeed (proxies + unblocking)
- BeautifulSoup: Extracts data from the HTML you received
- SQLite: Stores the extracted data

All four are necessary!

## Architecture

```
beijing-jobs-cli/
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point
│   ├── config.py               # Configuration management
│   ├── models.py               # Pydantic data models
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract base scraper class
│   │   ├── zhaopin.py         # Zhaopin scraper
│   │   ├── job51.py           # 51job scraper
│   │   ├── boss_zhipin.py     # BOSS Zhipin scraper
│   │   └── liepin.py          # Liepin scraper
│   ├── client/
│   │   ├── __init__.py
│   │   └── http_client.py     # httpx client with Bright Data integration
│   ├── cache/
│   │   ├── __init__.py
│   │   └── database.py        # SQLite cache management
│   ├── display/
│   │   ├── __init__.py
│   │   └── ui.py              # Rich UI components
│   └── utils/
│       ├── __init__.py
│       ├── parser.py          # Common parsing utilities
│       └── translator.py      # Optional: Chinese to English translation
├── tests/
│   ├── __init__.py
│   ├── test_scrapers.py
│   └── test_cache.py
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── config.yaml                # User configuration file
```

## Data Models

```python
# models.py structure
class JobPosting(BaseModel):
    id: str                      # Unique identifier
    title: str                   # Job title
    company: str                 # Company name
    location: str                # Beijing district
    salary_range: Optional[str]  # e.g., "20k-35k"
    experience: Optional[str]    # Required experience
    education: Optional[str]     # Education requirement
    description: str             # Job description
    requirements: List[str]      # List of requirements
    tags: List[str]              # Tech stack tags
    posted_date: datetime
    url: str                     # Link to original posting
    source: str                  # Platform name (zhaopin, 51job, etc.)
    fetched_at: datetime         # When we scraped it
```

## Features & CLI Commands

### Phase 1: Core Features
```bash
# Search for jobs
bjobs search "software engineer" --location beijing --salary-min 20k

# List recent jobs from cache
bjobs list --sort-by date --limit 20

# Show detailed job info
bjobs show <job-id>

# View jobs from specific platform
bjobs search --platform zhaopin "backend developer"

# Refresh cache (fetch new jobs)
bjobs refresh --all

# Show stats
bjobs stats  # Show request usage, cached jobs, etc.
```

### Phase 2: Enhanced Features
```bash
# Filter by tech stack
bjobs search --tech python,django,postgresql

# Export results
bjobs export --format json/csv output.json

# Watch mode (monitor for new jobs)
bjobs watch "senior python developer" --interval 6h

# Configure settings
bjobs config set bright_data.api_key "YOUR_KEY"
bjobs config show
```

## Implementation Plan

### Sprint 1: Foundation (Days 1-3)
- [ ] Set up project structure with uv
- [ ] Create base models (JobPosting, Config)
- [ ] Implement httpx client wrapper with Bright Data integration
- [ ] Set up SQLite cache with basic CRUD operations
- [ ] Create Rich display utilities (tables, panels)
- [ ] Basic CLI structure with Typer

### Sprint 2: First Scraper (Days 4-6)
- [ ] Implement base scraper abstract class
- [ ] Build BOSS Zhipin scraper (largest platform, start here)
  - [ ] Search results page parsing
  - [ ] Job detail page parsing
  - [ ] Handle pagination
- [ ] Implement caching logic (check cache first, then scrape)
- [ ] Add rate limiting (respect 5000 requests/month)
- [ ] Create `bjobs search` command

### Sprint 3: Additional Scrapers (Days 7-10)
- [ ] Implement 51job scraper
- [ ] Implement Zhaopin scraper
- [ ] Implement Liepin scraper
- [ ] Normalize data across different platforms
- [ ] Handle errors gracefully (captchas, blocks, etc.)

### Sprint 4: Enhanced Features (Days 11-14)
- [ ] Add filtering capabilities (salary, tech stack, experience)
- [ ] Implement `bjobs list`, `bjobs show` commands
- [ ] Add request counter/tracker (monitor Bright Data usage)
- [ ] Implement export functionality
- [ ] Add configuration management
- [ ] Write tests for core functionality

### Sprint 5: Polish & Documentation (Days 15-16)
- [ ] Add progress bars and loading indicators
- [ ] Improve error messages and help text
- [ ] Write comprehensive README
- [ ] Add usage examples
- [ ] Optional: Add translation support for Chinese text

## Bright Data Integration

### Setup
1. Sign up for Bright Data free tier
2. Get API credentials for Web MCP
3. Configure proxy/unlocker settings

### HTTP Client Configuration
```python
# Example httpx setup with Bright Data
import httpx

class BrightDataClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.requests_used = 0
        self.monthly_limit = 5000
        
    async def get(self, url: str, **kwargs):
        if self.requests_used >= self.monthly_limit:
            raise Exception("Monthly request limit reached!")
        
        # Configure Bright Data proxy
        proxies = {
            "http://": f"http://username:{self.api_key}@...",
            "https://": f"http://username:{self.api_key}@..."
        }
        
        async with httpx.AsyncClient(proxies=proxies, timeout=30.0) as client:
            response = await client.get(url, **kwargs)
            self.requests_used += 1
            return response
```

## Caching Strategy

### Cache Logic
1. **Check cache first**: Look for jobs less than 24 hours old
2. **Smart refresh**: Only fetch new jobs if cache is stale
3. **Incremental updates**: Only scrape first page daily, full refresh weekly
4. **Request tracking**: Store request count in SQLite

### Database Schema
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    salary_range TEXT,
    experience TEXT,
    education TEXT,
    description TEXT,
    requirements TEXT,  -- JSON array
    tags TEXT,          -- JSON array
    posted_date TEXT,
    url TEXT UNIQUE,
    source TEXT,
    fetched_at TEXT,
    is_active BOOLEAN DEFAULT 1
);

CREATE TABLE request_tracker (
    id INTEGER PRIMARY KEY,
    date TEXT,
    requests_count INTEGER,
    source TEXT
);

CREATE TABLE cache_metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);
```

## Request Optimization

### Strategies to Stay Under 5000/month
1. **Aggressive caching**: Cache everything for 24 hours minimum
2. **Smart scraping**: 
   - Only scrape first 2-3 pages per platform
   - Focus on recent postings (last 7 days)
3. **Batch operations**: Fetch multiple jobs in one session
4. **User controls**: Let user choose which platforms to search
5. **Request budget**: ~40 requests per day (rough estimate)
   - 4 platforms × 2 pages × 1 request = 8 requests per search
   - 1 detail page request per job clicked = varies
   - Estimated: 5-15 requests per daily usage

### Request Breakdown Example
```
Daily usage (conservative):
- Morning search: 8 requests (4 platforms, 2 pages each)
- View 3 job details: 3 requests
- Total: ~11 requests/day
- Monthly: ~330 requests (well under 5000!)

Weekly full refresh:
- 4 platforms × 5 pages × 1 request = 20 requests
- View 10 details = 10 requests
- Monthly: ~120 requests for weekly refreshes

Total monthly estimate: 450-500 requests
```

## Display Design (Rich UI)

### Search Results View
```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                     Beijing Software Engineering Jobs            ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Found 47 jobs (23 from cache, 24 new) | Requests used: 287/5000

┌────┬─────────────────────┬──────────────┬──────────┬────────┬──────────┐
│ ID │ Title               │ Company      │ Location │ Salary │ Source   │
├────┼─────────────────────┼──────────────┼──────────┼────────┼──────────┤
│ 1  │ Senior Python Dev   │ ByteDance    │ Beijing  │ 30-50k │ BOSS     │
│ 2  │ Backend Engineer    │ Tencent      │ Beijing  │ 25-45k │ Zhaopin  │
│ 3  │ Full Stack Dev      │ Meituan      │ Beijing  │ 28-40k │ 51job    │
└────┴─────────────────────┴──────────────┴──────────┴────────┴──────────┘

Use 'bjobs show <id>' to view details
```

### Detail View
```
╔════════════════════════════════════════════════════════════════╗
║               Senior Python Developer - ByteDance              ║
╚════════════════════════════════════════════════════════════════╝

📍 Location:  Beijing, Haidian District
💰 Salary:    30k-50k RMB/month
📅 Posted:    2024-12-10 (6 days ago)
🔗 Source:    BOSS Zhipin

Requirements:
  • 5+ years Python development experience
  • Experience with Django/Flask
  • Familiar with microservices architecture
  • Good understanding of databases (MySQL, Redis)

Tech Stack:
  [Python] [Django] [Docker] [Kubernetes] [AWS]

[View Online] [Save] [Skip]
```

## Configuration

### config.yaml
```yaml
bright_data:
  api_key: "${BRIGHT_DATA_API_KEY}"
  monthly_limit: 5000

search:
  default_location: "Beijing"
  default_role: "software engineer"
  results_per_page: 20
  max_pages_per_platform: 3

cache:
  expiry_hours: 24
  database_path: "~/.cache/beijing-jobs/jobs.db"

scrapers:
  enabled:
    - boss_zhipin
    - zhaopin
    - job51
    - liepin

display:
  show_chinese: true
  show_english_translation: false
  color_scheme: "monokai"
```

## Error Handling

### Graceful Degradation
1. **Captcha detected**: Skip platform, use cached data
2. **Rate limit hit**: Show warning, use only cached data
3. **Network error**: Retry with exponential backoff (max 3 times)
4. **Parsing error**: Log error, continue with other platforms
5. **Monthly limit reached**: Disable scraping, show cached data only

## Testing Strategy

### Unit Tests
- Test each scraper independently with mocked responses
- Test cache operations
- Test data model validation
- Test request tracking

### Integration Tests
- Test full search flow (search → parse → cache → display)
- Test configuration loading
- Test CLI commands

### Manual Testing
- Test with real websites (limited, use sparingly)
- Verify display on different terminal sizes
- Test error scenarios

## Future Enhancements (Post-MVP)

1. **Translation**: Integrate translation API for English speakers
2. **Notifications**: Email/webhook when matching jobs are posted
3. **Filtering**: Advanced filters (company size, funding stage)
4. **AI Matching**: Use Claude API to match jobs to user profile
5. **Application Tracking**: Track which jobs you've applied to
6. **Analytics**: Visualize salary trends, popular tech stacks
7. **Multiple Cities**: Extend beyond Beijing
8. **Web UI**: Optional simple web interface

## Development Timeline

**Total Estimated Time**: 16-20 days (part-time)

- Week 1: Foundation + First Scraper (MVP)
- Week 2: Additional Scrapers + Core Features
- Week 3: Polish + Documentation

**MVP Deliverable** (by end of Week 1):
- Working CLI with BOSS Zhipin scraper
- SQLite caching
- Basic search and list commands
- Rich terminal display

## Success Metrics

- ✅ Stay under 5000 requests/month
- ✅ Cache hit rate > 70%
- ✅ Find 50+ relevant jobs per search
- ✅ Response time < 5 seconds for cached results
- ✅ Clean, readable terminal output

## Getting Started

1. Clone repository
2. Install dependencies: `uv sync`
3. Copy `.env.example` to `.env` and add Bright Data API key
4. Run: `bjobs search "python developer"`

---

## Notes & Considerations

### Legal/Ethical
- ✅ Personal use only (not commercial)
- ✅ Respect robots.txt
- ✅ Reasonable rate limiting
- ✅ No data redistribution
- ✅ Proper attribution

### Technical Challenges
1. **Anti-bot measures**: Handled by Bright Data
2. **Dynamic content**: Use playwright if needed (increases requests)
3. **Chinese text**: Handle encoding properly (UTF-8)
4. **Different page structures**: Each platform has unique HTML
5. **Pagination**: Each platform handles it differently

### Why httpx over requests?
- Native async/await support
- Better performance
- Modern, actively maintained
- Built-in HTTP/2 support
- Cleaner API for timeouts and retries

### Why Rich over alternatives?
- Beautiful, modern terminal UI
- Excellent documentation
- Tables, progress bars, panels out of the box
- Syntax highlighting
- Emoji support

### Why Typer over Click/argparse?
- Modern Python (type hints)
- Automatic help generation
- Built on Click (proven)
- Excellent developer experience
- Less boilerplate

## Questions to Consider

1. **Translation**: Do you need automatic Chinese → English translation?
2. **Notification**: Want to be notified of new matching jobs?
3. **Platform priority**: Which platform should we start with?
4. **Data retention**: How long to keep old job postings?
5. **Export format**: Need to export to any specific format?

---

**Ready to start building!** 🚀

Next step: Set up the project structure and implement the HTTP client with Bright Data integration.
