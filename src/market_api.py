import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Tuple


class MarketAPI:
    """
    Handles interactions with Yahoo Finance and determines market states
    based on New York time.
    """

    def __init__(self, ticker_symbol: str):
        self.ticker_symbol = ticker_symbol
        self.tz = ZoneInfo("America/New_York")

    def get_market_state(self, ny_time: datetime) -> str:
        """
        Determines the current market state.
        
        Args:
            ny_time (datetime): Current time in New York.
            
        Returns:
            str: One of 'open', 'premarket', 'after_hours', or 'closed'.
        """
        if ny_time.weekday() >= 5:  # Saturday or Sunday
            return 'closed'

        time_float = ny_time.hour + (ny_time.minute / 60.0)

        if time_float < 4.0:
            return 'closed'
        elif time_float < 9.5:   # 9:30 AM
            return 'premarket'
        elif time_float < 16.0:  # 4:00 PM
            return 'open'
        elif time_float < 20.0:  # 8:00 PM
            return 'after_hours'
        else:
            return 'closed'

    def get_next_open_time(self, ny_time: datetime) -> datetime:
        """
        Calculates the next 4:00 AM ET weekday session for sleep optimization.
        
        Args:
            ny_time (datetime): Current time in New York.
            
        Returns:
            datetime: The exact datetime of the next market pre-open.
        """
        target_date = ny_time.date()

        # If it's already past 4:00 AM, the next premarket is at least tomorrow
        if ny_time.hour >= 4:
            target_date += timedelta(days=1)

        # Skip Saturday and Sunday
        while target_date.weekday() >= 5:
            target_date += timedelta(days=1)

        return datetime(
            target_date.year, 
            target_date.month, 
            target_date.day, 
            4, 0, 
            tzinfo=self.tz
        )

    def fetch_data(self) -> Tuple[bool, float, float, float, float]:
        """
        Fetches the latest pricing data for the ticker.
        
        Returns:
            Tuple containing:
                - has_error (bool): True if the fetch failed.
                - current_price (float)
                - change_pct (float)
                - day_high (float)
                - day_low (float)
        """
        try:
            ticker = yf.Ticker(self.ticker_symbol)
            todays_data = ticker.history(period='1d', prepost=True)

            if todays_data.empty:
                return True, 0.0, 0.0, 0.0, 0.0

            current_price = todays_data['Close'].iloc[-1]
            prev_close = ticker.fast_info['previous_close']
            change_pct = ((current_price - prev_close) / prev_close) * 100

            # Attempt to fetch high/low via fast_info, fallback to history dataframe
            try:
                day_high = ticker.fast_info['day_high']
                day_low = ticker.fast_info['day_low']
            except Exception:
                day_high = todays_data['High'].max()
                day_low = todays_data['Low'].min()

            return False, current_price, change_pct, day_high, day_low

        except Exception:
            return True, 0.0, 0.0, 0.0, 0.0