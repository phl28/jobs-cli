"""Job scrapers for various Chinese job platforms."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseScraper

# Registry of available scrapers
SCRAPERS: dict[str, type["BaseScraper"]] = {}


def register_scraper(name: str):
    """Decorator to register a scraper class."""

    def decorator(cls: type["BaseScraper"]) -> type["BaseScraper"]:
        SCRAPERS[name] = cls
        return cls

    return decorator


def get_scraper(name: str) -> type["BaseScraper"] | None:
    """Get a scraper class by name."""
    return SCRAPERS.get(name)


def get_available_scrapers() -> list[str]:
    """Get list of available scraper names."""
    return list(SCRAPERS.keys())
