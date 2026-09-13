import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.market_api import StockData
from src.ticker_icon import TickerIcon

CONFIG_CONTENT = """
TICKER=AMD,AAPL
COLOR_POSITIVE=#0FAF50
COLOR_NEGATIVE=#EB3C3C
COLOR_ERROR_BORDER=#FF2828
COLOR_OPEN=#E0FFE0
COLOR_PREMARKET=#FFFFE0
COLOR_AFTER_HOURS=#E0E0FF
COLOR_CLOSED=#323232
SCROLL_SPEED_MS=100
DISPLAY_SECONDS=1
"""


@pytest.fixture
def config_path(tmp_path):
    """Writes a valid config.cfg to a temp dir and returns its path."""
    path = tmp_path / "config.cfg"
    path.write_text(CONFIG_CONTENT)
    return str(path)


@pytest.fixture
def app(config_path):
    """A TickerIcon wired to a real (temp) config, with a mocked tray icon."""
    ticker_icon = TickerIcon(config_path)
    ticker_icon.tray_icon = MagicMock()
    return ticker_icon


def test_init_builds_placeholder_snapshot_for_every_ticker(app):
    assert set(app.snapshot.keys()) == {"AMD", "AAPL"}
    assert all(isinstance(data, StockData) for data in app.snapshot.values())


def test_on_quit_stops_running_and_the_tray_icon(app):
    mock_icon = MagicMock()
    app.running = True

    app.on_quit(mock_icon, MagicMock())

    assert app.running is False
    mock_icon.stop.assert_called_once()


class TestTogglePause:
    def test_first_call_pauses_and_shows_app_icon(self, app):
        app.on_toggle_pause(app.tray_icon, MagicMock())

        assert app.paused.is_set() is True
        assert app.tray_icon.icon is not None
        assert app.tray_icon.title == "TickerIcon (Paused)"

    def test_second_call_unpauses(self, app):
        app.on_toggle_pause(app.tray_icon, MagicMock())
        app.on_toggle_pause(app.tray_icon, MagicMock())

        assert app.paused.is_set() is False


def test_on_check_for_updates_starts_only_one_worker(app):
    menu_item = MagicMock()
    worker = MagicMock()

    with patch("src.ticker_icon.threading.Thread", return_value=worker) as thread:
        app.on_check_for_updates(app.tray_icon, menu_item)
        app.on_check_for_updates(app.tray_icon, menu_item)

    assert app.update_in_progress is True
    assert menu_item.enabled is False
    app.tray_icon.update_menu.assert_called_once()
    thread.assert_called_once_with(target=app._check_for_updates, daemon=True)
    worker.start.assert_called_once()


def test_check_for_updates_launches_new_installer_and_resets_guard(app):
    release = MagicMock(version="1.1.0")
    installer_path = Path("TickerIcon-Setup.exe")
    app.running = True
    app.update_in_progress = True
    app.update_menu_item = MagicMock()
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = release
    app.update_checker.download_installer.return_value = installer_path

    app._check_for_updates()

    app.update_checker.download_installer.assert_called_once_with(release)
    app.update_checker.launch_installer.assert_called_once_with(installer_path)
    assert app.running is False
    assert app.update_in_progress is False
    assert app.update_menu_item.enabled is True
    app.tray_icon.stop.assert_called_once()
    app.tray_icon.update_menu.assert_called_once()


def test_check_for_updates_notifies_and_resets_guard_on_failure(app):
    app.update_in_progress = True
    app.update_menu_item = MagicMock()
    app.update_checker = MagicMock()
    app.update_checker.check.side_effect = RuntimeError("network unavailable")

    app._check_for_updates()

    app.tray_icon.notify.assert_called_once_with(
        "Update failed: network unavailable", "TickerIcon"
    )
    assert app.update_in_progress is False
    assert app.update_menu_item.enabled is True
    app.tray_icon.update_menu.assert_called_once()


class TestInterruptibleSleep:
    def test_returns_immediately_when_not_running(self, app):
        app.running = False
        start = time.monotonic()
        app._interruptible_sleep(5)
        assert time.monotonic() - start < 1

    def test_stops_early_once_running_flips_to_false(self, app):
        app.running = True

        def flip_after_delay():
            time.sleep(0.05)
            app.running = False

        threading.Thread(target=flip_after_delay, daemon=True).start()

        start = time.monotonic()
        app._interruptible_sleep(5)

        assert time.monotonic() - start < 1


class TestShowValue:
    def test_sets_icon_image_and_tooltip(self, app):
        data = StockData(
            symbol="AMD", price=100.5, change_pct=1.23, day_high=105.0, day_low=95.0,
            state="open", exchange="Nasdaq", has_error=False,
        )

        app._show_value(data)

        assert app.tray_icon.icon is not None
        assert "AMD - Nasdaq (Open)" in app.tray_icon.title
        assert "Price: $100.50 (+1.23%)" in app.tray_icon.title
        assert "High: $105.00 | Low: $95.00" in app.tray_icon.title

    def test_includes_error_indicator_when_has_error(self, app):
        data = StockData(symbol="AMD", state="closed", has_error=True)

        app._show_value(data)

        assert "[Update Failed]" in app.tray_icon.title

    def test_omits_market_part_when_exchange_unknown(self, app):
        data = StockData(symbol="AMD", state="closed", exchange="")

        app._show_value(data)

        assert "AMD (Closed)" in app.tray_icon.title


class TestScrollSymbol:
    def test_updates_icon_at_least_once(self, app):
        app.running = True
        with patch("src.ticker_icon.time.sleep"):
            app._scroll_symbol("AMD", "open")

        assert app.tray_icon.icon is not None

    def test_exits_immediately_when_not_running(self, app):
        app.running = False
        with patch("src.ticker_icon.time.sleep") as mock_sleep:
            app._scroll_symbol("AMD", "open")

        mock_sleep.assert_not_called()


class TestFetchLoop:
    def test_updates_snapshot_from_the_api(self, app):
        fake_snapshot = {
            symbol: StockData(symbol=symbol, state="open") for symbol in app.config["tickers"]
        }

        def fake_fetch_all():
            app.running = False  # stop the loop after a single iteration
            return fake_snapshot

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_interruptible_sleep"):
            app._fetch_loop()

        assert app.snapshot == fake_snapshot

    def test_sleeps_until_next_open_when_every_market_is_closed(self, app):
        next_open = datetime.now(ZoneInfo("UTC")) + timedelta(hours=2)
        fake_snapshot = {
            symbol: StockData(symbol=symbol, state="closed", has_error=False, next_open=next_open)
            for symbol in app.config["tickers"]
        }

        def fake_fetch_all():
            app.running = False
            return fake_snapshot

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_interruptible_sleep") as mock_sleep:
            app._fetch_loop()

        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 60

    def test_uses_short_sleep_when_any_market_is_open(self, app):
        fake_snapshot = {
            "AMD": StockData(symbol="AMD", state="open"),
            "AAPL": StockData(symbol="AAPL", state="closed"),
        }

        def fake_fetch_all():
            app.running = False
            return fake_snapshot

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_interruptible_sleep") as mock_sleep:
            app._fetch_loop()

        mock_sleep.assert_called_once_with(60)


class TestDisplayLoop:
    def test_cycles_through_every_configured_ticker(self, app):
        seen_symbols = []

        def fake_scroll(symbol, state):
            seen_symbols.append(symbol)
            if len(seen_symbols) >= len(app.config["tickers"]) * 2:
                app.running = False

        app._scroll_symbol = fake_scroll
        app._show_value = MagicMock()
        app.running = True
        app.data_ready.set()

        with patch.object(app, "_interruptible_sleep"):
            app._display_loop()

        assert set(seen_symbols) == set(app.config["tickers"])

    def test_exits_immediately_when_not_running(self, app):
        app._scroll_symbol = MagicMock()
        app.running = False
        app.data_ready.set()

        app._display_loop()

        app._scroll_symbol.assert_not_called()

    def test_waits_for_first_fetch_before_showing_values(self, app):
        app._scroll_symbol = MagicMock()
        app.running = True

        def flip_after_delay():
            time.sleep(0.05)
            app.running = False

        threading.Thread(target=flip_after_delay, daemon=True).start()

        app._display_loop()

        app._scroll_symbol.assert_not_called()

    def test_shows_app_icon_and_skips_ticker_cycle_when_paused(self, app):
        app._scroll_symbol = MagicMock()
        app._show_value = MagicMock()
        app.running = True
        app.data_ready.set()
        app.paused.set()

        def unpause_then_stop():
            app.paused.clear()
            app.running = False

        with patch.object(app, "_wait_while_paused", side_effect=unpause_then_stop):
            app._display_loop()

        app._scroll_symbol.assert_not_called()
        app._show_value.assert_not_called()
        assert app.tray_icon.title == "TickerIcon (Paused)"


class TestFetchLoopPause:
    def test_skips_fetching_while_paused(self, app):
        app.running = True
        app.paused.set()
        app.api.fetch_all = MagicMock()

        def stop_after_delay(*_args):
            app.running = False

        with patch.object(app, "_wait_while_paused", side_effect=stop_after_delay):
            app._fetch_loop()

        app.api.fetch_all.assert_not_called()
