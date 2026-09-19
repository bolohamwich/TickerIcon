from unittest.mock import patch

from src.updater import LATEST_RELEASE_PAGE_URL, ReleaseInfo, UpdateChecker


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


def release_payload(tag_name="v1.1.0", html_url="https://github.com/bolohamwich/TickerIcon/releases/tag/v1.1.0"):
    return (
        "{"
        f'"tag_name": "{tag_name}", '
        f'"html_url": "{html_url}"'
        "}"
    ).encode()


def test_check_returns_newer_release():
    checker = UpdateChecker(current_version="1.0.0")
    response = FakeResponse(release_payload())

    with patch("src.updater.urlopen", return_value=response):
        release = checker.check()

    assert release == ReleaseInfo("1.1.0", "https://github.com/bolohamwich/TickerIcon/releases/tag/v1.1.0")


def test_check_returns_none_for_current_release():
    checker = UpdateChecker(current_version="1.1.0")

    with patch("src.updater.urlopen", return_value=FakeResponse(release_payload())):
        assert checker.check() is None


def test_check_falls_back_to_latest_page_for_non_https_html_url():
    checker = UpdateChecker(current_version="1.0.0")

    with patch(
        "src.updater.urlopen",
        return_value=FakeResponse(release_payload(html_url="http://example.test/release")),
    ):
        release = checker.check()

    assert release == ReleaseInfo("1.1.0", LATEST_RELEASE_PAGE_URL)


def test_check_falls_back_to_latest_page_when_html_url_missing():
    checker = UpdateChecker(current_version="1.0.0")
    payload = b'{"tag_name": "v1.1.0"}'

    with patch("src.updater.urlopen", return_value=FakeResponse(payload)):
        release = checker.check()

    assert release == ReleaseInfo("1.1.0", LATEST_RELEASE_PAGE_URL)
