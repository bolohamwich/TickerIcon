import itertools
import time
import threading
from datetime import datetime
from typing import Dict
from zoneinfo import ZoneInfo
import pystray

from src.market_api import MarketAPI, StockData
from src.icon_generator import IconGenerator
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
        self.display_thread = None

        # Latest fetched data per symbol, shared between the fetch and display
        # threads, guarded by self.lock.
        self.snapshot: Dict[str, StockData] = {
            symbol: StockData(symbol=symbol) for symbol in self.config['tickers']
        }
        self.lock = threading.Lock()

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

    def start(self):
        """Initializes and runs the system tray application."""
        self.running = True

        # Setup right-click menu
        self.update_menu_item = pystray.MenuItem(
            'Check for Updates', self.on_check_for_updates
        )
        menu = pystray.Menu(
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

    def on_settings(self, icon, menu_item):
        """Open a settings window from the tray menu.

        Args:
            icon (pystray.Icon): The tray icon instance.
            menu_item (pystray.MenuItem): The menu item that triggered the call.

        Returns:
            None: The settings window is created and run in the same thread as its Tk root.
        """
        try:
            window = ConfigWindow(self.config_path, self.config, on_save=self._apply_config)
            window.show()
        except RuntimeError as exc:
            self._notify(str(exc))

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
            self.config = config
            self.api = MarketAPI(self.config['tickers'])
            self.icon_gen = IconGenerator(self.config)
            self.snapshot = {
                symbol: StockData(symbol=symbol) for symbol in self.config['tickers']
            }
            self.data_ready.clear()

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
        try:
            release = self.update_checker.check()
            if release is None:
                self._notify("You are already running the latest version.")
                return

            self._notify(f"Downloading TickerIcon {release.version}...")
            installer_path = self.update_checker.download_installer(release)
            self.update_checker.launch_installer(installer_path)
            self.running = False
            if self.tray_icon is not None:
                self.tray_icon.stop()
        except Exception as error:
            self._notify(f"Update failed: {error}")
        finally:
            with self.update_lock:
                self.update_in_progress = False
            if self.update_menu_item is not None:
                self.update_menu_item.enabled = True
            if self.tray_icon is not None:
                self.tray_icon.update_menu()

    def _notify(self, message: str):
        if self.tray_icon is not None:
            self.tray_icon.notify(message, "TickerIcon")

    def _fetch_loop(self):
        """Background loop that periodically refreshes market data for all tickers."""
        while self.running:
            if self.paused.is_set():
                self._interruptible_sleep(0.25)
                continue

            with self.lock:
                api = self.api
                config_version = self.config

            snapshot = api.fetch_all()

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

            self._interruptible_sleep(sleep_seconds)

    def _display_loop(self):
        """Background loop that cycles through tickers, scrolling then showing each one."""
        while self.running and not self.data_ready.is_set():
            self.data_ready.wait(timeout=0.1)

        while self.running:
            if self.paused.is_set():
                self.tray_icon.icon = self.icon_gen.generate_app_icon()
                self.tray_icon.title = "TickerIcon (Paused)"
                self._wait_while_paused()
                continue

            with self.lock:
                symbols = list(self.config['tickers'])
                display_seconds = self.config['display_seconds']
                scroll_speed_ms = self.config['scroll_speed_ms']

            if not symbols:
                self._interruptible_sleep(0.25)
                continue

            for symbol in itertools.cycle(symbols):
                if not self.running:
                    return
                if self.paused.is_set():
                    break

                with self.lock:
                    current_symbols = list(self.config['tickers'])
                    if current_symbols != symbols:
                        break
                    data = self.snapshot.get(symbol, StockData(symbol=symbol))
                    display_seconds = self.config['display_seconds']
                    scroll_speed_ms = self.config['scroll_speed_ms']

                try:
                    self._scroll_symbol(symbol, data.state, scroll_speed_ms)
                except TypeError:
                    self._scroll_symbol(symbol, data.state)
                if not self.running:
                    return

                self._show_value(data)
                self._interruptible_sleep(display_seconds)

            if not self.running:
                return

    def _scroll_symbol(self, symbol: str, state: str, scroll_speed_ms: float = None):
        """
        Animates `symbol` scrolling right-to-left across the icon.

        Args:
            symbol (str): The ticker symbol to scroll, e.g. 'AMD'.
            state (str): Current market state, used for the background color.
            scroll_speed_ms (float, optional): Current scroll speed in ms per char.

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
            if not self.running or self.paused.is_set():
                return
            offset = int(distance * step / steps)
            self.tray_icon.icon = self.icon_gen.generate_scroll_frame(symbol, state, offset)
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

        state_formatted = data.state.replace("_", " ").title()
        err_indicator = " [Update Failed]" if data.has_error else ""
        market_part = f" - {data.exchange}" if data.exchange else ""

        tooltip = (
            f"{data.symbol}{market_part} ({state_formatted}){err_indicator}\n"
            f"Price: ${data.price:.2f} ({data.change_pct:+.2f}%)\n"
            f"High: ${data.day_high:.2f} | Low: ${data.day_low:.2f}"
        )
        self.tray_icon.title = tooltip

    def _interruptible_sleep(self, seconds: float):
        """
        Sleeps in small increments so shutdown via Quit is near-instant.

        Args:
            seconds (float): Total time to sleep for, in seconds.
        """
        end_time = time.monotonic() + seconds
        while self.running and not self.paused.is_set() and time.monotonic() < end_time:
            time.sleep(0.1)

    def _wait_while_paused(self):
        """Blocks until the app is unpaused or shutting down."""
        while self.running and self.paused.is_set():
            time.sleep(0.1)
