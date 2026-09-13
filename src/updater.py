import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.version import APP_VERSION

LATEST_RELEASE_URL = "https://api.github.com/repos/bolohamwich/TickerIcon/releases/latest"
INSTALLER_ASSET_NAME = "TickerIcon-Setup.exe"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    installer_url: str


class UpdateChecker:
    """Checks GitHub Releases and downloads the published Windows installer."""

    def __init__(
        self,
        current_version: str = APP_VERSION,
        release_url: str = LATEST_RELEASE_URL,
        installer_name: str = INSTALLER_ASSET_NAME,
        timeout: float = 10.0,
    ):
        self.current_version = current_version
        self.release_url = release_url
        self.installer_name = installer_name
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

        for asset in release.get("assets", []):
            if asset.get("name") != self.installer_name:
                continue
            url = str(asset.get("browser_download_url", ""))
            if urlparse(url).scheme != "https":
                raise ValueError("Release installer URL must use HTTPS")
            return ReleaseInfo(version=version, installer_url=url)

        raise ValueError(f"Release {tag_name!r} has no {self.installer_name} asset")

    def download_installer(self, release: ReleaseInfo) -> Path:
        """Download an installer to a temporary file and return its path."""
        request = Request(
            release.installer_url,
            headers={"Accept": "application/octet-stream", "User-Agent": "TickerIcon updater"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            with tempfile.NamedTemporaryFile(
                prefix="TickerIcon-Setup-", suffix=".exe", delete=False
            ) as installer_file:
                while chunk := response.read(1024 * 1024):
                    installer_file.write(chunk)
                return Path(installer_file.name)

    @staticmethod
    def launch_installer(installer_path: Path) -> None:
        """Start the installer independently so the application can exit."""
        subprocess.Popen([str(installer_path)], close_fds=True)


def _normalise_version(value: str) -> str:
    match = re.search(r"\d+(?:\.\d+)*", value.lstrip("vV"))
    return match.group(0) if match else ""


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))
