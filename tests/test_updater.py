from unittest.mock import patch

import pytest

from src.updater import ReleaseInfo, UpdateChecker


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size=-1):
        if size == -1:
            chunk = self.content[self.position:]
            self.position = len(self.content)
            return chunk
        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


def release_payload(tag_name="v1.1.0", asset_url="https://example.test/TickerIcon-Setup.exe"):
    return (
        "{"
        f'"tag_name": "{tag_name}", '
        '"assets": [{'
        '"name": "TickerIcon-Setup.exe", '
        f'"browser_download_url": "{asset_url}"'
        "}]"
        "}"
    ).encode()


def test_check_returns_newer_release():
    checker = UpdateChecker(current_version="1.0.0")
    response = FakeResponse(release_payload())

    with patch("src.updater.urlopen", return_value=response):
        release = checker.check()

    assert release == ReleaseInfo("1.1.0", "https://example.test/TickerIcon-Setup.exe")


def test_check_returns_none_for_current_release():
    checker = UpdateChecker(current_version="1.1.0")

    with patch("src.updater.urlopen", return_value=FakeResponse(release_payload())):
        assert checker.check() is None


def test_check_rejects_non_https_installer():
    checker = UpdateChecker()

    with patch(
        "src.updater.urlopen",
        return_value=FakeResponse(release_payload(asset_url="http://example.test/setup.exe")),
    ), pytest.raises(ValueError, match="HTTPS"):
        checker.check()


def test_download_installer_writes_temporary_file(tmp_path):
    checker = UpdateChecker()
    release = ReleaseInfo("1.1.0", "https://example.test/TickerIcon-Setup.exe")

    with patch("src.updater.urlopen", return_value=FakeResponse(b"installer data")), patch(
        "src.updater.tempfile.NamedTemporaryFile"
    ) as named_temporary_file:
        file_handle = named_temporary_file.return_value.__enter__.return_value
        file_handle.name = str(tmp_path / "TickerIcon-Setup.exe")
        checker.download_installer(release)

    file_handle.write.assert_called_once_with(b"installer data")
