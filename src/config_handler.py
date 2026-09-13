import configparser
from typing import List, Tuple, TypedDict

RGB = Tuple[int, int, int]

# yfinance has no batch quote endpoint; it issues one HTTP request per
# ticker, so the tracked symbol list is capped to keep polling reasonable.
MAX_TICKERS = 10


class AppConfig(TypedDict):
    tickers: List[str]
    color_positive: RGB
    color_negative: RGB
    color_error_border: RGB
    bg_open: RGB
    bg_premarket: RGB
    bg_after_hours: RGB
    bg_closed: RGB
    scroll_speed_ms: int
    display_seconds: float


class ConfigHandler:
    """
    Reads config.cfg and exposes its values as a typed dict, converting
    hex color strings into RGB tuples usable by the icon generator.
    """

    def __init__(self, config_path: str = "config.cfg"):
        """
        Args:
            config_path (str): Path to the config.cfg file to load.
        """
        self.config_path = config_path

    @staticmethod
    def _hex_to_rgb(value: str) -> RGB:
        """
        Converts a '#RRGGBB' hex string into an (R, G, B) tuple.

        Args:
            value (str): Hex color string, e.g. '#0FAF50'.

        Returns:
            RGB: The corresponding (R, G, B) tuple.
        """
        value = value.strip().lstrip('#')
        if len(value) != 6:
            raise ValueError(f"Invalid hex color '{value}'. Expected #RRGGBB.")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    @staticmethod
    def _rgb_to_hex(value: RGB) -> str:
        """Convert an RGB tuple into a hexadecimal color string.

        Args:
            value (RGB): An (R, G, B) tuple to convert.

        Returns:
            str: A '#RRGGBB' color string.
        """
        return '#%02X%02X%02X' % value

    def load(self) -> AppConfig:
        """
        Parses config.cfg into a typed configuration dict.

        Returns:
            AppConfig: The tracked ticker symbols, resolved RGB colors, and
                animation timing settings.
        """
        parser = configparser.ConfigParser()
        # config.cfg has no section headers, so provide a default one for configparser
        with open(self.config_path, "r") as f:
            content = f"[DEFAULT]\n{f.read()}"
        parser.read_string(content)
        section = parser["DEFAULT"]

        tickers = [s.strip().upper() for s in section["TICKER"].split(",") if s.strip()]
        if len(tickers) > MAX_TICKERS:
            tickers = tickers[:MAX_TICKERS]

        return AppConfig(
            tickers=tickers,
            color_positive=self._hex_to_rgb(section["COLOR_POSITIVE"]),
            color_negative=self._hex_to_rgb(section["COLOR_NEGATIVE"]),
            color_error_border=self._hex_to_rgb(section["COLOR_ERROR_BORDER"]),
            bg_open=self._hex_to_rgb(section["COLOR_OPEN"]),
            bg_premarket=self._hex_to_rgb(section["COLOR_PREMARKET"]),
            bg_after_hours=self._hex_to_rgb(section["COLOR_AFTER_HOURS"]),
            bg_closed=self._hex_to_rgb(section["COLOR_CLOSED"]),
            scroll_speed_ms=section.getint("SCROLL_SPEED_MS"),
            display_seconds=section.getfloat("DISPLAY_SECONDS"),
        )

    def save(self, config: AppConfig):
        """Persist a configuration dict to the on-disk config file.

        Args:
            config (AppConfig): A fully populated configuration dictionary.

        Returns:
            None: The file is written in-place at config_path.

        Raises:
            ValueError: If the ticker list or timing values are invalid.
            OSError: If the config file cannot be written.
        """
        tickers = [symbol.strip().upper() for symbol in config['tickers'] if symbol.strip()]
        if not tickers:
            raise ValueError("At least one ticker is required.")
        if len(tickers) > MAX_TICKERS:
            raise ValueError(f"Ticker list exceeds MAX_TICKERS ({MAX_TICKERS}).")

        scroll_speed_ms = int(config['scroll_speed_ms'])
        display_seconds = float(config['display_seconds'])
        if scroll_speed_ms <= 0:
            raise ValueError("SCROLL_SPEED_MS must be positive.")
        if display_seconds <= 0:
            raise ValueError("DISPLAY_SECONDS must be positive.")

        lines = [
            "# Symbols to track, comma separated (max 10 — yfinance issues one request per symbol)",
            f"TICKER={','.join(tickers)}",
            "",
            "# Text colors",
            f"COLOR_POSITIVE={self._rgb_to_hex(config['color_positive'])}",
            f"COLOR_NEGATIVE={self._rgb_to_hex(config['color_negative'])}",
            f"COLOR_ERROR_BORDER={self._rgb_to_hex(config['color_error_border'])}",
            "",
            "# Background colors",
            f"COLOR_OPEN={self._rgb_to_hex(config['bg_open'])}",
            f"COLOR_PREMARKET={self._rgb_to_hex(config['bg_premarket'])}",
            f"COLOR_AFTER_HOURS={self._rgb_to_hex(config['bg_after_hours'])}",
            f"COLOR_CLOSED={self._rgb_to_hex(config['bg_closed'])}",
            "",
            "# Ticker symbol scroll speed, in milliseconds per character",
            f"SCROLL_SPEED_MS={scroll_speed_ms}",
            "",
            "# How long the price is shown after scrolling (seconds)",
            f"DISPLAY_SECONDS={display_seconds}",
        ]

        with open(self.config_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
