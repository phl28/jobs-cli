"""SQLite database for caching jobs and tracking requests."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from ..config import get_settings
from ..models import JobPosting, RequestStats


class Database:
    """SQLite database manager for job caching and request tracking."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the database.

        Args:
            db_path: Path to SQLite database file. Uses settings default if not provided.
        """
        settings = get_settings()
        self.db_path = db_path or settings.database_path
        settings.ensure_cache_dir()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Ensure database tables are created."""
        if not self._initialized:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await self._init_tables(conn)
            self._initialized = True

    async def _init_tables(self, conn: aiosqlite.Connection) -> None:
        """Create database tables if they don't exist."""
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                salary_range TEXT,
                experience TEXT,
                education TEXT,
                description TEXT,
                requirements TEXT,
                tags TEXT,
                posted_date TEXT,
                url TEXT UNIQUE,
                source TEXT,
                fetched_at TEXT,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS request_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                requests_count INTEGER DEFAULT 0,
                UNIQUE(month)
            );

            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_jobs_fetched_at ON jobs(fetched_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
            """
        )
        await conn.commit()

    # === Job Operations ===

    async def save_job(self, job: JobPosting) -> None:
        """Save a single job to the database."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO jobs 
                (id, title, company, location, salary_range, experience, education,
                 description, requirements, tags, posted_date, url, source, fetched_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.title,
                    job.company,
                    job.location,
                    job.salary_range,
                    job.experience,
                    job.education,
                    job.description,
                    json.dumps(job.requirements),
                    json.dumps(job.tags),
                    job.posted_date.isoformat() if job.posted_date else None,
                    job.url,
                    job.source,
                    job.fetched_at.isoformat(),
                    1 if job.is_active else 0,
                ),
            )
            await conn.commit()

    async def save_jobs(self, jobs: list[JobPosting]) -> int:
        """Save multiple jobs to the database.

        Args:
            jobs: List of jobs to save

        Returns:
            Number of jobs saved
        """
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            for job in jobs:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO jobs 
                    (id, title, company, location, salary_range, experience, education,
                     description, requirements, tags, posted_date, url, source, fetched_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.id,
                        job.title,
                        job.company,
                        job.location,
                        job.salary_range,
                        job.experience,
                        job.education,
                        job.description,
                        json.dumps(job.requirements),
                        json.dumps(job.tags),
                        job.posted_date.isoformat() if job.posted_date else None,
                        job.url,
                        job.source,
                        job.fetched_at.isoformat(),
                        1 if job.is_active else 0,
                    ),
                )
            await conn.commit()
        return len(jobs)

    async def get_job(self, job_id: str) -> Optional[JobPosting]:
        """Get a single job by ID."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
            if row:
                return self._row_to_job(row)
        return None

    async def get_jobs(
        self,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobPosting]:
        """Get jobs from the database.

        Args:
            source: Filter by source platform
            limit: Maximum number of jobs to return
            offset: Offset for pagination

        Returns:
            List of jobs
        """
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if source:
                cursor = await conn.execute(
                    "SELECT * FROM jobs WHERE source = ? AND is_active = 1 ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
                    (source, limit, offset),
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM jobs WHERE is_active = 1 ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            rows = await cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    async def search_jobs(
        self,
        query: str,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> list[JobPosting]:
        """Search jobs by title, company, or description.

        Args:
            query: Search query
            source: Filter by source platform
            limit: Maximum results

        Returns:
            List of matching jobs
        """
        await self._ensure_initialized()
        search_pattern = f"%{query}%"
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if source:
                cursor = await conn.execute(
                    """
                    SELECT * FROM jobs 
                    WHERE is_active = 1 AND source = ?
                    AND (title LIKE ? OR company LIKE ? OR description LIKE ? OR tags LIKE ?)
                    ORDER BY fetched_at DESC LIMIT ?
                    """,
                    (source, search_pattern, search_pattern, search_pattern, search_pattern, limit),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT * FROM jobs 
                    WHERE is_active = 1
                    AND (title LIKE ? OR company LIKE ? OR description LIKE ? OR tags LIKE ?)
                    ORDER BY fetched_at DESC LIMIT ?
                    """,
                    (search_pattern, search_pattern, search_pattern, search_pattern, limit),
                )
            rows = await cursor.fetchall()
            return [self._row_to_job(row) for row in rows]

    async def delete_old_jobs(self, days: int = 30) -> int:
        """Delete jobs older than specified days.

        Args:
            days: Delete jobs older than this many days

        Returns:
            Number of jobs deleted
        """
        await self._ensure_initialized()
        cutoff = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM jobs WHERE fetched_at < date(?, '-' || ? || ' days')",
                (cutoff, days),
            )
            await conn.commit()
            return cursor.rowcount

    async def get_job_count(self, source: Optional[str] = None) -> int:
        """Get total number of jobs in cache."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            if source:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE source = ? AND is_active = 1",
                    (source,),
                )
            else:
                cursor = await conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active = 1")
            row = await cursor.fetchone()
            return row[0] if row else 0

    def _row_to_job(self, row: aiosqlite.Row) -> JobPosting:
        """Convert a database row to a JobPosting object."""
        return JobPosting(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"] or "Beijing",
            salary_range=row["salary_range"],
            experience=row["experience"],
            education=row["education"],
            description=row["description"],
            requirements=json.loads(row["requirements"]) if row["requirements"] else [],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            posted_date=datetime.fromisoformat(row["posted_date"]) if row["posted_date"] else None,
            url=row["url"],
            source=row["source"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            is_active=bool(row["is_active"]),
        )

    # === Request Tracking ===

    async def increment_request_count(self, count: int = 1) -> int:
        """Increment the request counter for the current month.

        Args:
            count: Number of requests to add

        Returns:
            New total for the month
        """
        await self._ensure_initialized()
        month = datetime.now().strftime("%Y-%m")
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO request_tracker (month, requests_count)
                VALUES (?, ?)
                ON CONFLICT(month) DO UPDATE SET requests_count = requests_count + ?
                """,
                (month, count, count),
            )
            await conn.commit()
            cursor = await conn.execute(
                "SELECT requests_count FROM request_tracker WHERE month = ?",
                (month,),
            )
            row = await cursor.fetchone()
            return row[0] if row else count

    async def get_monthly_usage(self) -> RequestStats:
        """Get request usage statistics for the current month."""
        await self._ensure_initialized()
        month = datetime.now().strftime("%Y-%m")
        settings = get_settings()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT requests_count FROM request_tracker WHERE month = ?",
                (month,),
            )
            row = await cursor.fetchone()
            requests_used = row[0] if row else 0
            return RequestStats(
                month=month,
                requests_used=requests_used,
                monthly_limit=settings.monthly_request_limit,
            )

    # === Cache Metadata ===

    async def set_metadata(self, key: str, value: str) -> None:
        """Set a cache metadata value."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO cache_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, datetime.now().isoformat()),
            )
            await conn.commit()

    async def get_metadata(self, key: str) -> Optional[str]:
        """Get a cache metadata value."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT value FROM cache_metadata WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_last_refresh(self, source: str) -> Optional[datetime]:
        """Get the last refresh time for a source."""
        value = await self.get_metadata(f"last_refresh_{source}")
        if value:
            return datetime.fromisoformat(value)
        return None

    async def set_last_refresh(self, source: str) -> None:
        """Set the last refresh time for a source to now."""
        await self.set_metadata(f"last_refresh_{source}", datetime.now().isoformat())

    async def is_cache_stale(self, source: str, hours: Optional[int] = None) -> bool:
        """Check if the cache for a source is stale.

        Args:
            source: Source platform name
            hours: Hours before considering stale (uses settings default if not provided)

        Returns:
            True if cache is stale or doesn't exist
        """
        settings = get_settings()
        hours = hours or settings.cache_expiry_hours
        last_refresh = await self.get_last_refresh(source)
        if not last_refresh:
            return True
        age = datetime.now() - last_refresh
        return age.total_seconds() > hours * 3600
