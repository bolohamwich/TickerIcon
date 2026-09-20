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


class TestNextSymbol:
    def test_click_requests_jump_when_multiple_symbols_enabled(self, app):
        app.on_next_symbol(app.tray_icon, MagicMock())

        assert app.skip_requested.is_set() is True

    def test_click_does_nothing_with_a_single_enabled_symbol(self, app):
        app.enabled_symbols = {"AMD"}

        app.on_next_symbol(app.tray_icon, MagicMock())

        assert app.skip_requested.is_set() is False


class TestSymbolToggles:
    def test_all_symbols_enabled_initially(self, app):
        assert app.enabled_symbols == {"AMD", "AAPL"}

    def test_toggle_disables_an_enabled_symbol(self, app):
        app.on_toggle_symbol("AAPL")

        assert app.enabled_symbols == {"AMD"}
        assert app.display_dirty.is_set() is True
        app.tray_icon.update_menu.assert_called_once()

    def test_toggle_reenables_a_disabled_symbol(self, app):
        app.enabled_symbols = {"AMD"}

        app.on_toggle_symbol("AAPL")

        assert app.enabled_symbols == {"AMD", "AAPL"}

    def test_last_enabled_symbol_cannot_be_disabled(self, app):
        app.enabled_symbols = {"AMD"}

        app.on_toggle_symbol("AMD")

        assert app.enabled_symbols == {"AMD"}
        app.tray_icon.update_menu.assert_not_called()

    def test_menu_lists_every_configured_symbol(self, app):
        items = app._symbol_menu_items()

        assert [item.text for item in items] == ["AMD", "AAPL"]

    def test_menu_checkmarks_track_enabled_state(self, app):
        app.enabled_symbols = {"AMD"}

        items = app._symbol_menu_items()

        assert [item.checked for item in items] == [True, False]

    def test_menu_item_click_toggles_its_symbol(self, app):
        items = app._symbol_menu_items()

        items[1](app.tray_icon)

        assert app.enabled_symbols == {"AMD"}


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

    def test_enables_new_tickers_and_keeps_toggle_state(self, app):
        app.enabled_symbols = {"AMD"}  # AAPL toggled off
        new_config = dict(app.config)
        new_config["tickers"] = ["AMD", "AAPL", "NVDA"]

        app._apply_config(new_config)

        assert app.enabled_symbols == {"AMD", "NVDA"}
        assert app.display_dirty.is_set() is True

    def test_enables_all_when_every_retained_ticker_was_disabled(self, app):
        app.enabled_symbols = {"AAPL"}
        new_config = dict(app.config)
        new_config["tickers"] = ["AMD"]

        app._apply_config(new_config)

        assert app.enabled_symbols == {"AMD"}


def _real_update_menu_item(app):
    """Returns the real pystray 'Check for Updates' item from the app's menu."""
    return next(item for item in app._build_menu().items if item.text == "Check for Updates")


def test_on_check_for_updates_starts_only_one_worker(app):
    # Use the real pystray MenuItem: a MagicMock hid the read-only .enabled crash
    menu_item = _real_update_menu_item(app)
    worker = MagicMock()

    with patch("src.ticker_icon.threading.Thread", return_value=worker) as thread:
        menu_item(app.tray_icon)
        menu_item(app.tray_icon)

    assert app.update_in_progress is True
    app.tray_icon.update_menu.assert_called_once()
    thread.assert_called_once_with(target=app._check_for_updates, daemon=True)
    worker.start.assert_called_once()


def test_update_menu_item_grays_out_while_check_in_progress(app):
    menu_item = _real_update_menu_item(app)

    assert menu_item.enabled is True

    app.update_in_progress = True

    assert menu_item.enabled is False


def test_check_for_updates_opens_download_page_when_user_accepts(app):
    release = MagicMock(version="1.1.0", download_page_url="https://github.com/bolohamwich/TickerIcon/releases/tag/v1.1.0")
    app.running = True
    app.update_in_progress = True
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = release

    with patch.object(app, "_open_checking_dialog", return_value=None) as progress, \
            patch.object(app, "_prompt_open_download_page", return_value=True) as prompt, \
            patch("src.ticker_icon.webbrowser.open") as browser_open:
        app._check_for_updates()

    progress.assert_called_once()
    prompt.assert_called_once_with(release)
    browser_open.assert_called_once_with(release.download_page_url, new=2)
    assert app.running is True
    assert app.update_in_progress is False
    app.tray_icon.stop.assert_not_called()
    app.tray_icon.update_menu.assert_called_once()


def test_check_for_updates_does_not_open_browser_when_user_declines(app):
    release = MagicMock(version="1.1.0", download_page_url="https://example.test/release")
    app.update_in_progress = True
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = release

    with patch.object(app, "_open_checking_dialog", return_value=None), \
            patch.object(app, "_prompt_open_download_page", return_value=False), \
            patch("src.ticker_icon.webbrowser.open") as browser_open:
        app._check_for_updates()

    browser_open.assert_not_called()
    assert app.update_in_progress is False
    app.tray_icon.update_menu.assert_called_once()


def test_check_for_updates_shows_dialog_when_already_up_to_date(app):
    app.update_in_progress = True
    app.update_checker = MagicMock()
    app.update_checker.check.return_value = None

    with patch.object(app, "_open_checking_dialog", return_value=None), \
            patch.object(app, "_show_up_to_date_dialog") as up_to_date, \
            patch("src.ticker_icon.webbrowser.open") as browser_open:
        app._check_for_updates()

    up_to_date.assert_called_once()
    browser_open.assert_not_called()
    assert app.update_in_progress is False


def test_check_for_updates_closes_progress_dialog_even_on_failure(app):
    app.update_in_progress = True
    app.update_checker = MagicMock()
    app.update_checker.check.side_effect = RuntimeError("boom")
    progress_dialog = MagicMock()

    with patch.object(app, "_open_checking_dialog", return_value=progress_dialog):
        app._check_for_updates()

    progress_dialog.destroy.assert_called_once()


def test_check_for_updates_notifies_and_resets_guard_on_failure(app):
    app.update_in_progress = True
    app.update_checker = MagicMock()
    app.update_checker.check.side_effect = RuntimeError("network unavailable")

    with patch.object(app, "_open_checking_dialog", return_value=None):
        app._check_for_updates()

    app.tray_icon.notify.assert_called_once_with(
        "Update check failed: network unavailable", "TickerIcon"
    )
    assert app.update_in_progress is False
    app.tray_icon.update_menu.assert_called_once()


class TestCheckingDialog:
    def test_open_renders_a_topmost_checking_box(self, app):
        fake_root = MagicMock()
        fake_tk = MagicMock()
        fake_tk.Tk.return_value = fake_root

        with patch("src.ticker_icon.tk", fake_tk):
            dialog = app._open_checking_dialog()

        assert dialog is fake_root
        fake_tk.Label.assert_called_once()
        assert "Checking for updates" in fake_tk.Label.call_args[1]["text"]
        fake_root.update.assert_called_once()

    def test_open_returns_none_without_tkinter(self, app):
        with patch("src.ticker_icon.tk", None):
            assert app._open_checking_dialog() is None

    def test_close_destroys_the_dialog(self, app):
        dialog = MagicMock()

        app._close_checking_dialog(dialog)

        dialog.destroy.assert_called_once()

    def test_close_ignores_none(self, app):
        app._close_checking_dialog(None)


class TestUpToDateDialog:
    def test_shows_info_dialog(self, app):
        fake_root = MagicMock()
        fake_tk = MagicMock()
        fake_tk.Tk.return_value = fake_root
        fake_messagebox = MagicMock()

        with patch("src.ticker_icon.tk", fake_tk), \
                patch("src.ticker_icon.messagebox", fake_messagebox):
            app._show_up_to_date_dialog()

        fake_messagebox.showinfo.assert_called_once_with(
            "TickerIcon Update",
            "TickerIcon is already at the latest version.",
            parent=fake_root,
        )
        fake_root.destroy.assert_called_once()

    def test_falls_back_to_notification_without_tkinter(self, app):
        with patch("src.ticker_icon.tk", None), patch("src.ticker_icon.messagebox", None):
            app._show_up_to_date_dialog()

        app.tray_icon.notify.assert_called_once_with(
            "TickerIcon is already at the latest version.", "TickerIcon"
        )


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

    def test_returns_immediately_when_skip_requested(self, app):
        app.running = True
        app.skip_requested.set()

        start = time.monotonic()
        app._interruptible_sleep(5)

        assert time.monotonic() - start < 1

    def test_returns_immediately_when_display_dirty(self, app):
        app.running = True
        app.display_dirty.set()

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

    def test_exits_immediately_when_skip_requested(self, app):
        app.running = True
        app.skip_requested.set()
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

    def test_fetches_disabled_symbols_too(self, app):
        app.enabled_symbols = {"AMD"}  # AAPL toggled off in the display
        requested = set()

        def fake_fetch_all(previous=None):
            requested.update(previous.keys())
            app.running = False
            return dict(previous)

        app.api.fetch_all = fake_fetch_all
        app.running = True

        with patch.object(app, "_sleep_between_fetches"):
            app._fetch_loop()

        assert requested == {"AMD", "AAPL"}

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

    def test_skips_disabled_symbols_in_the_cycle(self, app):
        app.config["tickers"] = ["AMD", "AAPL", "NVDA"]
        app.snapshot["NVDA"] = StockData(symbol="NVDA")
        app.enabled_symbols = {"AMD", "NVDA"}
        seen_symbols = []

        def fake_scroll(symbol, state):
            seen_symbols.append(symbol)
            if len(seen_symbols) >= 4:
                app.running = False

        app._scroll_symbol = fake_scroll
        app._show_value = MagicMock()
        app.running = True
        app.data_ready.set()

        with patch.object(app, "_interruptible_sleep"):
            app._display_loop()

        assert set(seen_symbols) == {"AMD", "NVDA"}

    def test_skip_request_jumps_to_next_symbol_without_showing_value(self, app):
        seen_symbols = []

        def fake_scroll(symbol, state):
            seen_symbols.append(symbol)
            app.skip_requested.set()  # click arrived during the name scroll
            if len(seen_symbols) >= 3:
                app.running = False

        app._scroll_symbol = fake_scroll
        app._show_value = MagicMock()
        app.running = True
        app.data_ready.set()

        with patch.object(app, "_interruptible_sleep"):
            app._display_loop()

        app._show_value.assert_not_called()
        assert seen_symbols == ["AMD", "AAPL", "AMD"]

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

    def test_single_enabled_symbol_shows_static_value(self, app):
        app.enabled_symbols = {"AMD"}  # AAPL toggled off
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

    def test_builds_strip_from_enabled_symbols_only(self, app):
        app.enabled_symbols = {"AMD"}
        app.running = True
        app.continuous_gen = MagicMock()
        app.continuous_gen.width = 0

        app._display_continuous_lap()

        assert app.continuous_gen.build.call_args[0][0] == ["AMD"]

    def test_skip_request_jumps_to_the_next_segment(self, app):
        app.running = True
        app.skip_requested.set()
        app.continuous_gen = MagicMock()
        app.continuous_gen.width = 40
        app.continuous_gen.next_segment_offset.return_value = 25
        app.continuous_gen.symbol_at.return_value = None
        app.continuous_gen.render_frame.return_value = "frame"

        with patch("src.ticker_icon.time.sleep"), \
                patch.object(app, "_continuous_pixels_per_frame", return_value=20):
            app._display_continuous_lap()

        app.continuous_gen.next_segment_offset.assert_called_once_with(0)
        app.continuous_gen.render_frame.assert_called_once_with(25)
        assert app.skip_requested.is_set() is False

    def test_returns_when_enabled_symbols_change_mid_lap(self, app):
        app.running = True
        app.continuous_gen = MagicMock()
        app.continuous_gen.width = 10000
        app.continuous_gen.symbol_at.return_value = None

        def render_and_toggle(offset):
            app.display_dirty.set()  # a symbol was toggled mid-lap
            return "frame"

        app.continuous_gen.render_frame.side_effect = render_and_toggle

        with patch("src.ticker_icon.time.sleep"), \
                patch.object(app, "_continuous_pixels_per_frame", return_value=1):
            app._display_continuous_lap()

        assert app.continuous_gen.render_frame.call_count == 1


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
