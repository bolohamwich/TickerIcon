import threading
import time
from datetime import datetime, timedelta
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
CONTINUOUS_SCROLL=false
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


class TestOnSettings:
    def test_runs_window_on_a_daemon_thread(self, app):
        worker = MagicMock()

        with patch("src.ticker_icon.threading.Thread", return_value=worker) as thread:
            app.on_settings(app.tray_icon, MagicMock())

        thread.assert_called_once_with(target=app._run_settings_window, daemon=True)
        worker.start.assert_called_once()
        assert app.settings_open is True

    def test_does_not_open_a_second_window_while_one_is_open(self, app):
        worker = MagicMock()

        with patch("src.ticker_icon.threading.Thread", return_value=worker) as thread:
            app.on_settings(app.tray_icon, MagicMock())
            app.on_settings(app.tray_icon, MagicMock())

        thread.assert_called_once()

    def test_run_settings_window_releases_guard_on_close(self, app):
        app.settings_open = True

        with patch("src.ticker_icon.ConfigWindow") as window_cls:
            app._run_settings_window()

        window_cls.return_value.show.assert_called_once()
        assert app.settings_open is False

    def test_run_settings_window_notifies_and_releases_guard_on_error(self, app):
        app.settings_open = True

        with patch("src.ticker_icon.ConfigWindow", side_effect=RuntimeError("no tk")):
            app._run_settings_window()

        app.tray_icon.notify.assert_called_once_with("no tk", "TickerIcon")
        assert app.settings_open is False


class TestApplyConfig:
    def test_preserves_fetched_data_for_retained_tickers(self, app):
        fetched = StockData(symbol="AMD", price=123.0, change_pct=4.5, state="open")
        app.snapshot["AMD"] = fetched
        app.data_ready.set()

        app._apply_config(dict(app.config))

        assert app.snapshot["AMD"] is fetched
        assert app.data_ready.is_set() is True

    def test_clears_data_ready_when_a_new_ticker_is_added(self, app):
        app.data_ready.set()
        new_config = dict(app.config)
        new_config["tickers"] = ["AMD", "AAPL", "NVDA"]

        app._apply_config(new_config)

        assert app.data_ready.is_set() is False
        assert set(app.snapshot.keys()) == {"AMD", "AAPL", "NVDA"}


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


def test_check_for_updates_opens_download_page_when_user_accepts(app):
    release = MagicMock(version="1.1.0", download_page_url="https://github.com/bolohamwich/TickerIcon/releases/tag/v1.1.0")
    app.running = True
    app.update_in_progress = True
    app.update_menu_item = MagicMock()
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = release

    with patch.object(app, "_prompt_open_download_page", return_value=True) as prompt, \
            patch("src.ticker_icon.webbrowser.open") as browser_open:
        app._check_for_updates()

    prompt.assert_called_once_with(release)
    browser_open.assert_called_once_with(release.download_page_url, new=2)
    assert app.running is True
    assert app.update_in_progress is False
    assert app.update_menu_item.enabled is True
    app.tray_icon.stop.assert_not_called()
    app.tray_icon.update_menu.assert_called_once()


def test_check_for_updates_does_not_open_browser_when_user_declines(app):
    release = MagicMock(version="1.1.0", download_page_url="https://example.test/release")
    app.update_in_progress = True
    app.update_menu_item = MagicMock()
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = release

    with patch.object(app, "_prompt_open_download_page", return_value=False), \
            patch("src.ticker_icon.webbrowser.open") as browser_open:
        app._check_for_updates()

    browser_open.assert_not_called()
    assert app.update_in_progress is False
    assert app.update_menu_item.enabled is True
    app.tray_icon.update_menu.assert_called_once()


def test_check_for_updates_notifies_when_already_up_to_date(app):
    app.update_in_progress = True
    app.update_menu_item = MagicMock()
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = None

    with patch("src.ticker_icon.webbrowser.open") as browser_open:
        app._check_for_updates()

    app.tray_icon.notify.assert_called_once_with(
        "You are already running the latest version.", "TickerIcon"
    )
    browser_open.assert_not_called()
    assert app.update_in_progress is False


def test_check_for_updates_notifies_and_resets_guard_on_failure(app):
    app.update_in_progress = True
    app.update_menu_item = MagicMock()
    app.update_checker = MagicMock()
    app.update_checker.check.side_effect = RuntimeError("network unavailable")

    app._check_for_updates()

    app.tray_icon.notify.assert_called_once_with(
        "Update check failed: network unavailable", "TickerIcon"
    )
    assert app.update_in_progress is False
    assert app.update_menu_item.enabled is True
    app.tray_icon.update_menu.assert_called_once()


class TestPromptOpenDownloadPage:
    def test_returns_true_when_user_clicks_yes(self, app):
        release = MagicMock(version="1.1.0", download_page_url="https://example.test/release")
        fake_root = MagicMock()
        fake_tk = MagicMock()
        fake_tk.Tk.return_value = fake_root
        fake_messagebox = MagicMock()
        fake_messagebox.askyesno.return_value = True

        with patch("src.ticker_icon.tk", fake_tk), \
                patch("src.ticker_icon.messagebox", fake_messagebox):
            result = app._prompt_open_download_page(release)

        assert result is True
        fake_messagebox.askyesno.assert_called_once_with(
            "TickerIcon Update",
            "New version 1.1.0 available!\nOpen the download page?",
            parent=fake_root,
        )
        fake_root.withdraw.assert_called_once()
        fake_root.destroy.assert_called_once()

    def test_returns_false_when_user_clicks_no(self, app):
        release = MagicMock(version="1.1.0", download_page_url="https://example.test/release")
        fake_tk = MagicMock()
        fake_messagebox = MagicMock()
        fake_messagebox.askyesno.return_value = False

        with patch("src.ticker_icon.tk", fake_tk), \
                patch("src.ticker_icon.messagebox", fake_messagebox):
            result = app._prompt_open_download_page(release)

        assert result is False

    def test_destroys_root_even_when_dialog_raises(self, app):
        release = MagicMock(version="1.1.0", download_page_url="https://example.test/release")
        fake_root = MagicMock()
        fake_tk = MagicMock()
        fake_tk.Tk.return_value = fake_root
        fake_messagebox = MagicMock()
        fake_messagebox.askyesno.side_effect = RuntimeError("boom")

        with patch("src.ticker_icon.tk", fake_tk), \
                patch("src.ticker_icon.messagebox", fake_messagebox), \
                pytest.raises(RuntimeError):
            app._prompt_open_download_page(release)

        fake_root.destroy.assert_called_once()

    def test_falls_back_to_notification_without_tkinter(self, app):
        release = MagicMock(version="1.1.0", download_page_url="https://example.test/release")

        with patch("src.ticker_icon.tk", None), patch("src.ticker_icon.messagebox", None):
            result = app._prompt_open_download_page(release)

        assert result is False
        app.tray_icon.notify.assert_called_once_with(
            "New version 1.1.0 available! Download it from https://example.test/release",
            "TickerIcon",
        )


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

    def test_passes_has_error_to_scroll_frame(self, app):
        app.running = True
        app.icon_gen.generate_scroll_frame = MagicMock(return_value=app.icon_gen.generate_loading_frame())

        with patch("src.ticker_icon.time.sleep"):
            app._scroll_symbol("AMD", "open", scroll_speed_ms=50, has_error=True)

        assert app.icon_gen.generate_scroll_frame.call_args.kwargs["has_error"] is True


class TestFetchLoop:
    def test_updates_snapshot_from_the_api(self, app):
        fake_snapshot = {
            symbol: StockData(symbol=symbol, state="open") for symbol in app.config["tickers"]
        }

        def fake_fetch_all(previous=None):
            app.running = False  # stop the loop after a single iteration
            return fake_snapshot

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_interruptible_sleep"):
            app._fetch_loop()

        assert app.snapshot == fake_snapshot

    def test_passes_previous_snapshot_to_fetch_all(self, app):
        received = []

        def fake_fetch_all(previous=None):
            received.append(previous)
            app.running = False
            return dict(previous)

        initial_snapshot = app.snapshot
        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_sleep_between_fetches"):
            app._fetch_loop()

        assert received == [initial_snapshot]

    def test_sleeps_until_next_open_when_every_market_is_closed(self, app):
        next_open = datetime.now(ZoneInfo("UTC")) + timedelta(hours=2)
        fake_snapshot = {
            symbol: StockData(symbol=symbol, state="closed", has_error=False, next_open=next_open)
            for symbol in app.config["tickers"]
        }

        def fake_fetch_all(previous=None):
            app.running = False
            return fake_snapshot

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_sleep_between_fetches") as mock_sleep:
            app._fetch_loop()

        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] >= 60

    def test_uses_short_sleep_when_any_market_is_open(self, app):
        fake_snapshot = {
            "AMD": StockData(symbol="AMD", state="open"),
            "AAPL": StockData(symbol="AAPL", state="closed"),
        }

        def fake_fetch_all(previous=None):
            app.running = False
            return fake_snapshot

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_sleep_between_fetches") as mock_sleep:
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

    def test_shows_app_icon_and_loading_title_while_data_not_ready(self, app):
        app._scroll_symbol = MagicMock()
        app.running = True

        def flip_after_delay():
            time.sleep(0.05)
            app.running = False

        threading.Thread(target=flip_after_delay, daemon=True).start()

        app._display_loop()

        assert app.tray_icon.icon is not None
        assert app.tray_icon.title == "TickerIcon (Loading...)"

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


class TestDisplayLoopSingleSymbol:
    def test_shows_value_without_scrolling_the_name(self, app):
        app.config["tickers"] = ["AMD"]
        app._scroll_symbol = MagicMock()
        app._show_value = MagicMock()
        app.running = True
        app.data_ready.set()

        def stop(_seconds):
            app.running = False

        with patch.object(app, "_interruptible_sleep", side_effect=stop):
            app._display_loop()

        app._scroll_symbol.assert_not_called()
        app._show_value.assert_called_once()

    def test_stays_static_even_in_continuous_scroll_mode(self, app):
        app.config["tickers"] = ["AMD"]
        app.config["continuous_scroll"] = True
        app._show_value = MagicMock()
        app.running = True
        app.data_ready.set()

        def stop(_seconds):
            app.running = False

        with patch.object(app, "_display_continuous_lap") as lap, \
                patch.object(app, "_interruptible_sleep", side_effect=stop):
            app._display_loop()

        lap.assert_not_called()
        app._show_value.assert_called_once()


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


class TestSleepBetweenFetches:
    def test_returns_immediately_when_data_ready_cleared(self, app):
        app.running = True
        app.data_ready.clear()

        start = time.monotonic()
        app._sleep_between_fetches(5)

        assert time.monotonic() - start < 1


class TestDisplayContinuousLap:
    def test_builds_strip_and_renders_until_width_reached(self, app):
        app.running = True
        app.continuous_gen = MagicMock()
        app.continuous_gen.width = 40
        app.continuous_gen.render_frame.return_value = "frame"
        app.continuous_gen.symbol_at.return_value = None

        with patch("src.ticker_icon.time.sleep"), \
                patch.object(app, "_continuous_pixels_per_frame", return_value=20):
            app._display_continuous_lap()

        app.continuous_gen.build.assert_called_once()
        assert app.tray_icon.icon == "frame"
        assert app.continuous_gen.render_frame.call_count == 2

    def test_updates_tooltip_when_new_symbol_enters_view(self, app):
        app.running = True
        data_amd = StockData(symbol="AMD", change_pct=1.0, state="open")
        app.continuous_gen = MagicMock()
        app.continuous_gen.width = 10
        app.continuous_gen.render_frame.return_value = "frame"
        app.continuous_gen.symbol_at.return_value = data_amd

        with patch("src.ticker_icon.time.sleep"), \
                patch.object(app, "_continuous_pixels_per_frame", return_value=10):
            app._display_continuous_lap()

        assert "AMD" in app.tray_icon.title

    def test_stops_immediately_when_paused_mid_lap(self, app):
        app.running = True
        app.paused.set()
        app.continuous_gen = MagicMock()
        app.continuous_gen.width = 1000

        with patch("src.ticker_icon.time.sleep"), \
                patch.object(app, "_continuous_pixels_per_frame", return_value=1):
            app._display_continuous_lap()

        app.continuous_gen.render_frame.assert_not_called()

    def test_sleeps_when_no_symbols_configured(self, app):
        app.config["tickers"] = []

        with patch.object(app, "_interruptible_sleep") as mock_sleep:
            app._display_continuous_lap()

        mock_sleep.assert_called_once_with(0.25)


class TestContinuousPixelsPerFrame:
    def test_returns_at_least_one(self, app):
        assert app._continuous_pixels_per_frame(100000) >= 1

    def test_faster_speed_yields_more_pixels_per_frame(self, app):
        slow = app._continuous_pixels_per_frame(1000)
        fast = app._continuous_pixels_per_frame(100)
        assert fast > slow


class TestDisplayLoopContinuousRouting:
    def test_routes_to_continuous_lap_when_enabled(self, app):
        app.running = True
        app.data_ready.set()
        app.config["continuous_scroll"] = True

        def stop_after_lap():
            app.running = False

        with patch.object(app, "_display_continuous_lap", side_effect=stop_after_lap) as lap:
            app._display_loop()

        lap.assert_called_once()
