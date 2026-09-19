import itertools
import time
import threading
import webbrowser
from datetime import datetime
from typing import Dict
from zoneinfo import ZoneInfo
import pystray

try:
    import tkinter as tk
    from tkinter import messagebox
except ModuleNotFoundError:  # pragma: no cover - only affects headless/non-Windows test environments
    tk = None
    messagebox = None

from src.market_api import MarketAPI, StockData
from src.icon_generator import IconGenerator
from src.continuous_scroll import ContinuousScrollGenerator
from src.config_handler import ConfigHandler
from src.config_window import ConfigWindow
from src.updater import UpdateChecker

# Animation frame rate for the ticker symbol scroll (higher = smoother, more CPU)
SCROLL_FRAME_INTERVAL_S = 0.04


class TickerIcon:
    """
    Main application controller. Runs two independent background threads —
    one polling market data, one driving the icon animation — so a slow or
    failed API call never stalls the tray icon's visuals.
    """

    def __init__(self, config_path: str = "config.cfg"):
        """
        Args:
            config_path (str): Path to the config.cfg file to load.
        """
        self.config_path = config_path
        self.config = ConfigHandler(config_path).load()
        self.api = MarketAPI(self.config['tickers'])
        self.icon_gen = IconGenerator(self.config)
        self.continuous_gen = ContinuousScrollGenerator(self.icon_gen)
        self.display_thread = None

        # Latest fetched data per symbol, shared between the fetch and display
        # threads, guarded by self.lock.
        self.snapshot: Dict[str, StockData] = {
            symbol: StockData(symbol=symbol) for symbol in self.config['tickers']
        }
        self.lock = threading.Lock()

        # Symbols currently shown by the display loop (quick menu toggles);
        # data is still fetched for every configured ticker. Guarded by self.lock.
        self.enabled_symbols = set(self.config['tickers'])

        # Set by the icon-click handler to jump the display to the next symbol.
        self.skip_requested = threading.Event()

        # Set when the enabled-symbol set changes so display loops re-read it.
        self.display_dirty = threading.Event()

        # Set once the first fetch completes, so the display loop doesn't
        # show stale/zeroed data before real data is available.
        self.data_ready = threading.Event()

        self.running = False
        self.tray_icon = None
        self.paused = threading.Event()
        self.update_checker = UpdateChecker()
        self.update_lock = threading.Lock()
        self.update_in_progress = False
        self.update_menu_item = None
        self.settings_lock = threading.Lock()
        self.settings_open = False

    def start(self):
        """Initializes and runs the system tray application."""
        self.running = True

        # Setup right-click menu
        self.update_menu_item = pystray.MenuItem(
            'Check for Updates', self.on_check_for_updates
        )
        menu = pystray.Menu(
            # default=True makes a left click on the icon trigger this item
            pystray.MenuItem('Next Symbol', self.on_next_symbol, default=True),
            pystray.MenuItem('Symbols', pystray.Menu(self._symbol_menu_items)),
            pystray.MenuItem('Settings', self.on_settings),
            pystray.MenuItem('Pause', self.on_toggle_pause, checked=lambda item: self.paused.is_set()),
            self.update_menu_item,
            pystray.MenuItem('Quit', self.on_quit),
        )

        # Generate initial placeholder icon
        first_symbol = self.config['tickers'][0]
        initial_image = self.icon_gen.generate_app_icon()
        self.tray_icon = pystray.Icon(
            "stock_ticker",
            initial_image,
            title=f"Loading {first_symbol}...",
            menu=menu
        )

        # Start the background fetch and display loops
        threading.Thread(target=self._fetch_loop, daemon=True).start()
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()

        # Run system tray (this blocks the main thread until closed)
        self.tray_icon.run()

    def on_quit(self, icon, menu_item):
        """
        Callback for the Quit menu option.

        Args:
            icon (pystray.Icon): The tray icon instance to stop.
            menu_item (pystray.MenuItem): The menu item that was clicked.
        """
        self.running = False
        icon.stop()

    def on_next_symbol(self, icon, menu_item):
        """
        Default tray action, triggered by clicking the icon: jumps the
        display to the next enabled symbol immediately. Does nothing when
        fewer than two symbols are enabled.

        Args:
            icon (pystray.Icon): The tray icon instance.
            menu_item (pystray.MenuItem): The menu item that was activated.
        """
        if len(self._get_enabled_symbols()) > 1:
            self.skip_requested.set()

    def on_toggle_symbol(self, symbol: str):
        """
        Toggles a symbol's visibility in the display rotation. This is a
        view-only filter: data is still fetched for every configured
        symbol. The last enabled symbol cannot be disabled.

        Args:
            symbol (str): The configured ticker symbol to toggle.
        """
        with self.lock:
            if symbol in self.enabled_symbols:
                enabled = [s for s in self.config['tickers'] if s in self.enabled_symbols]
                if len(enabled) <= 1:
                    return
                self.enabled_symbols.discard(symbol)
            else:
                self.enabled_symbols.add(symbol)
        self.display_dirty.set()
        if self.tray_icon is not None:
            self.tray_icon.update_menu()

    def _get_enabled_symbols(self):
        """
        Returns:
            List[str]: The enabled symbols, in configuration order.
        """
        with self.lock:
            return [s for s in self.config['tickers'] if s in self.enabled_symbols]

    def _symbol_menu_items(self):
        """
        Generates the dynamic 'Symbols' submenu: one checkable item per
        configured ticker, rebuilt every time the menu opens so it tracks
        config saves and quick toggles.

        Returns:
            List[pystray.MenuItem]: The submenu items.
        """
        with self.lock:
            symbols = list(self.config['tickers'])

        def make_action(symbol):
            # pystray rejects actions with >2 args, so bind via closure
            return lambda icon, item: self.on_toggle_symbol(symbol)

        return [
            pystray.MenuItem(
                symbol,
                make_action(symbol),
                checked=lambda item, s=symbol: s in self.enabled_symbols,
            )
            for symbol in symbols
        ]

    def _consume_skip(self) -> bool:
        """
        Clears a pending next-symbol request, if any.

        Returns:
            bool: True if a jump was requested since the last call.
        """
        if self.skip_requested.is_set():
            self.skip_requested.clear()
            return True
        return False

    def on_settings(self, icon, menu_item):
        """Open a settings window from the tray menu.

        Args:
            icon (pystray.Icon): The tray icon instance.
            menu_item (pystray.MenuItem): The menu item that triggered the call.

        Returns:
            None: The window runs on its own daemon thread so the tray menu
                handler is never blocked and shutdown is never held up.
        """
        with self.settings_lock:
            if self.settings_open:
                return
            self.settings_open = True
        threading.Thread(target=self._run_settings_window, daemon=True).start()

    def _run_settings_window(self):
        """Creates and runs the settings window, releasing the reopen guard on close.

        Returns:
            None: Blocks its own thread until the window is closed.
        """
        try:
            window = ConfigWindow(self.config_path, self.config, on_save=self._apply_config)
            window.show()
        except RuntimeError as exc:
            self._notify(str(exc))
        finally:
            with self.settings_lock:
                self.settings_open = False

    def on_toggle_pause(self, icon, menu_item):
        """
        Callback for the Pause menu checkbox. Freezes the fetch/display loops
        and shows the static application icon while paused.

        Args:
            icon (pystray.Icon): The tray icon instance.
            menu_item (pystray.MenuItem): The menu item that was clicked.
        """
        if self.paused.is_set():
            self.paused.clear()
        else:
            self.paused.set()
            icon.icon = self.icon_gen.generate_app_icon()
            icon.title = "TickerIcon (Paused)"

    def _apply_config(self, config):
        """Reloads the in-memory runtime state after a config save.

        Args:
            config (dict): The updated application configuration.

        Returns:
            None: The active fetch/display loops are synchronized with the new values.
        """
        with self.lock:
            old_snapshot = self.snapshot
            self.config = config
            self.api = MarketAPI(self.config['tickers'])
            self.icon_gen = IconGenerator(self.config)
            self.continuous_gen = ContinuousScrollGenerator(self.icon_gen)
            # Keep already-fetched data for retained tickers so a settings save
            # (e.g. toggling scroll mode) never shows zeroed placeholders.
            self.snapshot = {
                symbol: old_snapshot.get(symbol, StockData(symbol=symbol))
                for symbol in self.config['tickers']
            }
            if any(symbol not in old_snapshot for symbol in self.config['tickers']):
                self.data_ready.clear()
            # Keep quick-toggle states for retained tickers; new tickers start enabled
            old_enabled = self.enabled_symbols
            self.enabled_symbols = {
                symbol for symbol in self.config['tickers']
                if symbol in old_enabled or symbol not in old_snapshot
            }
            if not self.enabled_symbols:
                self.enabled_symbols = set(self.config['tickers'])
        self.display_dirty.set()

        if self.tray_icon is not None:
            self.tray_icon.notify("Settings saved. TickerIcon will use the new configuration.", "TickerIcon")

    def on_check_for_updates(self, icon, menu_item):
        """Checks for updates in the background so the tray menu stays responsive."""
        with self.update_lock:
            if self.update_in_progress:
                return
            self.update_in_progress = True

        menu_item.enabled = False
        icon.update_menu()
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    def _check_for_updates(self):
        """
        Checks GitHub for a newer release and, if one exists, asks the user
        whether to open its download page in the default browser.

        Returns:
            None: Runs on the update worker thread; always releases the
                in-progress guard and re-enables the menu item.
        """
        try:
            release = self.update_checker.check()
            if release is None:
                self._notify("You are already running the latest version.")
                return

            if self._prompt_open_download_page(release):
                # new=2 opens a new tab when a browser is already running
                if not webbrowser.open(release.download_page_url, new=2):
                    self._notify("Could not open the download page in your default browser.")
        except Exception as error:
            self._notify(f"Update check failed: {error}")
        finally:
            with self.update_lock:
                self.update_in_progress = False
            if self.update_menu_item is not None:
                self.update_menu_item.enabled = True
            if self.tray_icon is not None:
                self.tray_icon.update_menu()

    def _prompt_open_download_page(self, release) -> bool:
        """
        Shows a standard Yes/No dialog announcing the new version.

        Args:
            release (ReleaseInfo): The newer release found on GitHub.

        Returns:
            bool: True if the user chose to open the download page.
        """
        if tk is None or messagebox is None:
            self._notify(
                f"New version {release.version} available! "
                f"Download it from {release.download_page_url}"
            )
            return False

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)  # tray-triggered dialog has no parent window to raise it
        try:
            return bool(messagebox.askyesno(
                "TickerIcon Update",
                f"New version {release.version} available!\nOpen the download page?",
                parent=root,
            ))
        finally:
            root.destroy()

    def _notify(self, message: str):
        if self.tray_icon is not None:
            self.tray_icon.notify(message, "TickerIcon")

    def _fetch_loop(self):
        """Background loop that periodically refreshes market data for all tickers."""
        while self.running:
            if self.paused.is_set():
                self._wait_while_paused()
                continue

            with self.lock:
                api = self.api
                config_version = self.config
                previous_snapshot = self.snapshot

            # Pass the last snapshot so failed fetches keep showing last known values
            snapshot = api.fetch_all(previous_snapshot)

            with self.lock:
                if api is not self.api or config_version is not self.config:
                    continue
                self.snapshot = snapshot
                self.data_ready.set()

            all_closed = all(
                data.state == 'closed' and not data.has_error
                for data in snapshot.values()
            )

            if all_closed:
                next_open = MarketAPI.get_next_open_time(snapshot)
                if next_open is not None:
                    now = datetime.now(ZoneInfo("UTC"))
                    sleep_seconds = max(60, int((next_open - now).total_seconds()))
                else:
                    sleep_seconds = 60
            else:
                sleep_seconds = 60

            self._sleep_between_fetches(sleep_seconds)

    def _sleep_between_fetches(self, seconds: float):
        """
        Sleeps between fetches, waking early on shutdown, pause, or when a
        config save cleared data_ready (new tickers need an immediate fetch).

        Args:
            seconds (float): Maximum time to sleep for, in seconds.
        """
        end_time = time.monotonic() + seconds
        while (self.running and not self.paused.is_set()
                and self.data_ready.is_set() and time.monotonic() < end_time):
            time.sleep(0.1)

    def _display_loop(self):
        """Background loop that cycles through the enabled tickers, scrolling then showing each one."""
        while self.running:
            if self.paused.is_set():
                self.tray_icon.icon = self.icon_gen.generate_app_icon()
                self.tray_icon.title = "TickerIcon (Paused)"
                self._wait_while_paused()
                continue

            if not self.data_ready.is_set():
                self.tray_icon.icon = self.icon_gen.generate_app_icon()
                self.tray_icon.title = "TickerIcon (Loading...)"
                self.data_ready.wait(timeout=0.1)
                continue

            # Clear before reading so a toggle landing after the read still wakes us
            self.display_dirty.clear()
            with self.lock:
                enabled = [s for s in self.config['tickers'] if s in self.enabled_symbols]
                continuous_scroll = self.config['continuous_scroll']

            # With a single enabled symbol the name scroll is just noise: the
            # tooltip already identifies it, so keep the value on screen permanently.
            if len(enabled) == 1:
                with self.lock:
                    data = self.snapshot.get(enabled[0], StockData(symbol=enabled[0]))
                self.skip_requested.clear()  # nothing to jump to
                self._show_value(data)
                self._interruptible_sleep(1.0)
                continue

            if continuous_scroll:
                self._display_continuous_lap()
                if not self.running:
                    return
                continue

            with self.lock:
                display_seconds = self.config['display_seconds']
                scroll_speed_ms = self.config['scroll_speed_ms']

            if not enabled:
                self._interruptible_sleep(0.25)
                continue

            for symbol in itertools.cycle(enabled):
                if not self.running:
                    return
                if self.paused.is_set():
                    break

                with self.lock:
                    current_enabled = [s for s in self.config['tickers'] if s in self.enabled_symbols]
                    if (current_enabled != enabled or self.config['continuous_scroll']
                            or len(current_enabled) == 1):
                        break
                    data = self.snapshot.get(symbol, StockData(symbol=symbol))
                    display_seconds = self.config['display_seconds']
                    scroll_speed_ms = self.config['scroll_speed_ms']

                try:
                    self._scroll_symbol(symbol, data.state, scroll_speed_ms, has_error=data.has_error)
                except TypeError:
                    self._scroll_symbol(symbol, data.state)
                if not self.running:
                    return

                # A click during the name scroll advances straight to the next symbol
                if self._consume_skip():
                    continue

                self._show_value(data)
                self._interruptible_sleep(display_seconds)
                self._consume_skip()

            if not self.running:
                return

    def _display_continuous_lap(self):
        """
        Runs one full pass of the continuous-scroll strip, built from the
        enabled tickers/snapshot captured at the start of the lap so a fetch
        that completes mid-lap never causes a visible rewind or reset.

        Returns:
            None: Frames are rendered directly onto the tray icon until the
                strip has fully scrolled past, the enabled symbols change,
                or the app stops/pauses.
        """
        self.display_dirty.clear()
        with self.lock:
            enabled = [s for s in self.config['tickers'] if s in self.enabled_symbols]
            scroll_speed_ms = self.config['scroll_speed_ms']
            snapshot = dict(self.snapshot)
            continuous_gen = self.continuous_gen

        if not enabled:
            self._interruptible_sleep(0.25)
            return

        continuous_gen.build(enabled, snapshot)
        pixels_per_frame = self._continuous_pixels_per_frame(scroll_speed_ms)

        offset = 0
        last_symbol = None
        while offset < continuous_gen.width:
            if not self.running or self.paused.is_set():
                return
            if self.display_dirty.is_set():
                return  # enabled symbols changed; rebuild the strip next lap

            if self._consume_skip():
                offset = continuous_gen.next_segment_offset(offset)

            data = continuous_gen.symbol_at(offset)
            if data is not None and data.symbol != last_symbol:
                self._update_tooltip(data)
                last_symbol = data.symbol

            self.tray_icon.icon = continuous_gen.render_frame(offset)
            time.sleep(SCROLL_FRAME_INTERVAL_S)
            offset += pixels_per_frame

    def _continuous_pixels_per_frame(self, scroll_speed_ms: float) -> int:
        """
        Converts the configured per-character scroll speed into a pixel
        step for the continuous-scroll strip's animation frame cadence.

        Args:
            scroll_speed_ms (float): Configured milliseconds-per-character scroll speed.

        Returns:
            int: Pixels to advance the strip offset on each animation frame (at least 1).
        """
        avg_char_width = max(self.icon_gen.measure_text_width("0123456789") / 10, 1)
        chars_per_second = 1000.0 / scroll_speed_ms
        pixels_per_second = chars_per_second * avg_char_width
        return max(1, round(pixels_per_second * SCROLL_FRAME_INTERVAL_S))

    def _scroll_symbol(self, symbol: str, state: str, scroll_speed_ms: float = None, has_error: bool = False):
        """
        Animates `symbol` scrolling right-to-left across the icon.

        Args:
            symbol (str): The ticker symbol to scroll, e.g. 'AMD'.
            state (str): Current market state, used for the background color.
            scroll_speed_ms (float, optional): Current scroll speed in ms per char.
            has_error (bool): Whether the latest fetch for this symbol failed.

        Returns:
            None: One animation frame sequence is rendered onto the tray icon.
        """
        if scroll_speed_ms is None:
            with self.lock:
                scroll_speed_ms = self.config['scroll_speed_ms']

        text_width = self.icon_gen.measure_text_width(symbol)
        distance = 64 + text_width

        duration_s = max(len(symbol), 1) * (scroll_speed_ms / 1000.0)
        steps = max(int(duration_s / SCROLL_FRAME_INTERVAL_S), 1)

        for step in range(steps + 1):
            if not self.running or self.paused.is_set() or self.skip_requested.is_set():
                return
            offset = int(distance * step / steps)
            self.tray_icon.icon = self.icon_gen.generate_scroll_frame(symbol, state, offset, has_error=has_error)
            time.sleep(SCROLL_FRAME_INTERVAL_S)

    def _show_value(self, data: StockData):
        """
        Updates the icon and tooltip to show a ticker's latest price change.

        Args:
            data (StockData): The ticker snapshot to display.
        """
        self.tray_icon.icon = self.icon_gen.generate_value_frame(
            data.change_pct, data.state, has_error=data.has_error
        )
        self._update_tooltip(data)

    def _update_tooltip(self, data: StockData):
        """
        Refreshes only the tray tooltip for a ticker, without touching the icon image.

        Args:
            data (StockData): The ticker snapshot to describe in the tooltip.

        Returns:
            None: The tray icon's title is updated in place.
        """
        self.tray_icon.title = self._build_tooltip(data)

    @staticmethod
    def _build_tooltip(data: StockData) -> str:
        """
        Formats a ticker's tooltip text.

        Args:
            data (StockData): The ticker snapshot to describe.

        Returns:
            str: The multi-line tooltip text for the tray icon.
        """
        state_formatted = data.state.replace("_", " ").title()
        err_indicator = " [Update Failed]" if data.has_error else ""
        market_part = f" - {data.exchange}" if data.exchange else ""

        return (
            f"{data.symbol}{market_part} ({state_formatted}){err_indicator}\n"
            f"Price: ${data.price:.2f} ({data.change_pct:+.2f}%)\n"
            f"High: ${data.day_high:.2f} | Low: ${data.day_low:.2f}"
        )

    def _interruptible_sleep(self, seconds: float):
        """
        Sleeps in small increments, waking early on shutdown, pause, a
        next-symbol jump request, or an enabled-symbol change.

        Args:
            seconds (float): Total time to sleep for, in seconds.
        """
        end_time = time.monotonic() + seconds
        while (self.running and not self.paused.is_set()
                and not self.skip_requested.is_set() and not self.display_dirty.is_set()
                and time.monotonic() < end_time):
            time.sleep(0.1)

    def _wait_while_paused(self):
        """Blocks until the app is unpaused or shutting down."""
        while self.running and self.paused.is_set():
            time.sleep(0.1)
