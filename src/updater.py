import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.version import APP_VERSION

LATEST_RELEASE_URL = "https://api.github.com/repos/bolohamwich/TickerIcon/releases/latest"

# Fallback download page when the API response has no usable HTTPS html_url
LATEST_RELEASE_PAGE_URL = "https://github.com/bolohamwich/TickerIcon/releases/latest"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    download_page_url: str


class UpdateChecker:
    """Checks GitHub Releases for a version newer than the running one."""

    def __init__(
        self,
        current_version: str = APP_VERSION,
        release_url: str = LATEST_RELEASE_URL,
        timeout: float = 10.0,
    ):
        self.current_version = current_version
        self.release_url = release_url
        self.timeout = timeout

    def check(self) -> Optional[ReleaseInfo]:
        """Return the latest release when it is newer than the current version."""
        request = Request(
            self.release_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "TickerIcon updater",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            release = json.load(response)

        tag_name = str(release.get("tag_name", ""))
        version = _normalise_version(tag_name)
        if not version or _version_key(version) <= _version_key(self.current_version):
            return None

        download_page_url = str(release.get("html_url", ""))
        if urlparse(download_page_url).scheme != "https":
            download_page_url = LATEST_RELEASE_PAGE_URL
        return ReleaseInfo(version=version, download_page_url=download_page_url)


def _normalise_version(value: str) -> str:
    match = re.search(r"\d+(?:\.\d+)*", value.lstrip("vV"))
    return match.group(0) if match else ""


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))
