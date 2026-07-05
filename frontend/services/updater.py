"""Non-blocking update checker."""

import re
from dataclasses import dataclass

import httpx
from loguru import logger

CURRENT_VERSION = "1.0.0"
# Placeholder URL; in a real app this would point to a releases JSON file or GitHub API
UPDATE_CHECK_URL = (
    "https://api.github.com/repos/abdelouakil8/gestion-de-stock/releases/latest"
)


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    release_notes: str


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a semver string into a tuple of ints for comparison."""
    # Strip leading 'v'
    version_str = version_str.lstrip("v")
    parts = re.split(r"[-+.]", version_str)
    return tuple(int(p) for p in parts if p.isdigit())


def check_for_update(current_version: str = CURRENT_VERSION) -> UpdateInfo | None:
    """Check for updates synchronously. Never raises exceptions.
    Designed to be called from a background worker thread."""
    try:
        # 5 second timeout to avoid blocking startup too long if network is bad
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(UPDATE_CHECK_URL)
            if resp.status_code != 200:
                logger.debug(f"Update check failed with status {resp.status_code}")
                return None

            data = resp.json()
            latest_version = data.get("tag_name", "")
            if not latest_version:
                return None

            latest_parsed = _parse_version(latest_version)
            current_parsed = _parse_version(current_version)

            if latest_parsed > current_parsed:
                download_url = data.get("html_url", "")
                release_notes = data.get("body", "Nouvelle version disponible.")

                return UpdateInfo(
                    version=latest_version,
                    download_url=download_url,
                    release_notes=release_notes,
                )
    except Exception as e:
        logger.debug(f"Update check failed gracefully: {e}")

    return None
