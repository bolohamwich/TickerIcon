import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
import pystray
from pystray import MenuItem as item

from src.market_api import MarketAPI
from src.icon_generator import IconGenerator


class TickerIcon:
    """
    Main application controller. Manages the background polling thread,
    system tray lifecycle, and UI updates.
    """

    def __init__(self, ticker: str = "AMD"):
        self.ticker = ticker
        self.api = MarketAPI(ticker)
        self.icon_gen = IconGenerator()
        
        self.running = False
        self.tray_icon = None

    def start(self):
        """Initializes and runs the system tray application."""
        self.running = True
        
        # Setup right-click menu
        menu = pystray.Menu(item('Quit', self.on_quit))
        
        # Generate initial placeholder icon
        initial_image = self.icon_gen.generate(0.0, 'closed')
        self.tray_icon = pystray.Icon(
            "stock_ticker", 
            initial_image, 
            title=f"Loading {self.ticker}...", 
            menu=menu
        )

        # Start the background fetch loop
        worker_thread = threading.Thread(target=self._update_loop, daemon=True)
        worker_thread.start()

        # Run system tray (this blocks the main thread until closed)
        self.tray_icon.run()

    def on_quit(self, icon: pystray, item: object):
        """Callback for the Quit menu option."""
        self.running = False
        icon.stop()

    def _update_loop(self):
        """Background loop that fetches data, updates UI, and manages sleep states."""
        # Cache variables to display stale data gracefully during transient errors
        last_price, last_change_pct = 0.0, 0.0
        day_high, day_low = 0.0, 0.0
        has_error = False

        while self.running:
            ny_time = datetime.now(ZoneInfo("America/New_York"))
            state = self.api.get_market_state(ny_time)

            # Fetch fresh data
            error, current_price, change_pct, d_high, d_low = self.api.fetch_data()
            
            if error:
                has_error = True
            else:
                has_error = False
                last_price = current_price
                last_change_pct = change_pct
                day_high = d_high
                day_low = d_low

            # Update System Tray Icon Image
            self.tray_icon.icon = self.icon_gen.generate(
                last_change_pct, 
                state, 
                has_error=has_error
            )

            # Construct and apply tooltip
            state_formatted = state.replace("_", " ").title()
            err_indicator = " [Update Failed]" if has_error else ""
            
            tooltip = (
                f"{self.ticker} ({state_formatted}){err_indicator}\n"
                f"Price: ${last_price:.2f} ({last_change_pct:+.2f}%)\n"
                f"High: ${day_high:.2f} | Low: ${day_low:.2f}"
            )
            self.tray_icon.title = tooltip

            # Calculate sleep duration
            if state == 'closed' and not has_error:
                next_open = self.api.get_next_open_time(ny_time)
                sleep_seconds = max(60, int((next_open - ny_time).total_seconds()))
            else:
                sleep_seconds = 60

            # Interruptible sleep loop allows instant shutdown when Quit is clicked
            for _ in range(sleep_seconds):
                if not self.running:
                    return
                time.sleep(1)


if __name__ == "__main__":
    app = TickerIcon(ticker="AMD")
    app.start()