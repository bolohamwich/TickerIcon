import configparser
from typing import Dict, List, Tuple, TypedDict

RGB = Tuple[int, int, int]

# yfinance has no batch quote endpoint; it issues one HTTP request per
# ticker, so the tracked symbol list is capped to keep polling reasonable.
MAX_TICKERS = 10

# Default icon font size in pixels; ~44 is the largest that still fits '9.9' in the 64px icon.
DEFAULT_FONT_SIZE = 36

# Default height of the market-state/error strip at the bottom of the icon, in pixels.
DEFAULT_STRIP_WIDTH = 2

# Largest allowed strip height; anything bigger starts eating into the text area.
MAX_STRIP_WIDTH = 16

# Market states that each have their own color scheme, in display order.
MARKET_STATES = ('open', 'premarket', 'after_hours', 'closed')

# Fallback colors used when a config file predates per-state color schemes.
DEFAULT_BG_COLOR: RGB = (50, 50, 50)
DEFAULT_ERROR_COLOR: RGB = (255, 40, 40)
DEFAULT_POSITIVE_COLOR: RGB = (15, 175, 80)
DEFAULT_NEGATIVE_COLOR: RGB = (235, 60, 60)
DEFAULT_STRIP_COLORS: Dict[str, RGB] = {
    'open': (224, 255, 224),
    'premarket': (255, 255, 224),
    'after_hours': (224, 224, 255),
    'closed': (50, 50, 50),
}


class StateColors(TypedDict):
    positive: RGB
    negative: RGB
    strip: RGB


class AppConfig(TypedDict):
    tickers: List[str]
    bg_color: RGB
    error_color: RGB
    state_colors: Dict[str, StateColors]
    scroll_speed_ms: int
    display_ms: int
    continuous_scroll: bool
    font_size: int
    strip_width: int


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

    def _read_color(self, section, keys, default: RGB) -> RGB:
        """Reads the first present color key from a config section.

        Args:
            section (configparser.SectionProxy): The parsed config section.
            keys (Iterable[str]): Config keys to try in order; later entries
                are legacy names kept for backward compatibility.
            default (RGB): Color returned when none of the keys are present.

        Returns:
            RGB: The resolved (R, G, B) color.
        """
        for key in keys:
            if key in section:
                return self._hex_to_rgb(section[key])
        return default

    def load(self) -> AppConfig:
        """
        Parses config.cfg into a typed configuration dict, accepting both
        the current per-state color keys and the legacy shared-color keys.

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

        scroll_speed_ms = section.getint("SCROLL_SPEED_MS")
        if "DISPLAY_MS" in section:
            display_ms = section.getint("DISPLAY_MS")
        else:
            # Legacy configs stored the display time in seconds
            display_ms = round(section.getfloat("DISPLAY_SECONDS") * 1000)
        font_size = section.getint("FONT_SIZE", fallback=DEFAULT_FONT_SIZE)
        strip_width = section.getint("STRIP_WIDTH", fallback=DEFAULT_STRIP_WIDTH)
        if scroll_speed_ms <= 0:
            raise ValueError("SCROLL_SPEED_MS must be positive.")
        if display_ms <= 0:
            raise ValueError("DISPLAY_MS must be positive.")
        if font_size <= 0:
            raise ValueError("FONT_SIZE must be positive.")
        if not 0 <= strip_width <= MAX_STRIP_WIDTH:
            raise ValueError(f"STRIP_WIDTH must be between 0 and {MAX_STRIP_WIDTH}.")

        state_colors: Dict[str, StateColors] = {}
        for state in MARKET_STATES:
            prefix = f"COLOR_{state.upper()}"
            state_colors[state] = StateColors(
                positive=self._read_color(section, (f"{prefix}_POSITIVE", "COLOR_POSITIVE"), DEFAULT_POSITIVE_COLOR),
                negative=self._read_color(section, (f"{prefix}_NEGATIVE", "COLOR_NEGATIVE"), DEFAULT_NEGATIVE_COLOR),
                strip=self._read_color(section, (f"{prefix}_STRIP", prefix), DEFAULT_STRIP_COLORS[state]),
            )

        return AppConfig(
            tickers=tickers,
            bg_color=self._read_color(section, ("COLOR_BACKGROUND", "COLOR_CLOSED"), DEFAULT_BG_COLOR),
            error_color=self._read_color(section, ("COLOR_ERROR", "COLOR_ERROR_BORDER"), DEFAULT_ERROR_COLOR),
            state_colors=state_colors,
            scroll_speed_ms=scroll_speed_ms,
            display_ms=display_ms,
            continuous_scroll=section.getboolean("CONTINUOUS_SCROLL", fallback=True),
            font_size=font_size,
            strip_width=strip_width,
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
        display_ms = int(config['display_ms'])
        font_size = int(config.get('font_size', DEFAULT_FONT_SIZE))
        strip_width = int(config.get('strip_width', DEFAULT_STRIP_WIDTH))
        if scroll_speed_ms <= 0:
            raise ValueError("SCROLL_SPEED_MS must be positive.")
        if display_ms <= 0:
            raise ValueError("DISPLAY_MS must be positive.")
        if font_size <= 0:
            raise ValueError("FONT_SIZE must be positive.")
        if not 0 <= strip_width <= MAX_STRIP_WIDTH:
            raise ValueError(f"STRIP_WIDTH must be between 0 and {MAX_STRIP_WIDTH}.")

        state_colors = config['state_colors']
        missing_states = [state for state in MARKET_STATES if state not in state_colors]
        if missing_states:
            raise ValueError(f"Missing color scheme for market states: {', '.join(missing_states)}.")

        lines = [
            "# Symbols to track, comma separated (max 10 — yfinance issues one request per symbol)",
            f"TICKER={','.join(tickers)}",
            "",
            "# Static icon background color",
            f"COLOR_BACKGROUND={self._rgb_to_hex(config['bg_color'])}",
            "",
            "# Strip color shown when a data fetch fails",
            f"COLOR_ERROR={self._rgb_to_hex(config['error_color'])}",
            "",
            "# Per-market-state colors: positive/negative percentage text and the bottom strip",
        ]
        for state in MARKET_STATES:
            scheme = state_colors[state]
            prefix = f"COLOR_{state.upper()}"
            lines += [
                f"{prefix}_POSITIVE={self._rgb_to_hex(scheme['positive'])}",
                f"{prefix}_NEGATIVE={self._rgb_to_hex(scheme['negative'])}",
                f"{prefix}_STRIP={self._rgb_to_hex(scheme['strip'])}",
            ]
        lines += [
            "",
            "# Ticker symbol scroll speed, in milliseconds per character",
            f"SCROLL_SPEED_MS={scroll_speed_ms}",
            "",
            "# How long each price stays visible after scrolling, in milliseconds",
            f"DISPLAY_MS={display_ms}",
            "",
            "# Scroll every tracked symbol continuously in one line instead of one at a time",
            f"CONTINUOUS_SCROLL={'true' if config.get('continuous_scroll', True) else 'false'}",
            "",
            "# Icon font size in pixels (values above ~44 may clip the percentage text)",
            f"FONT_SIZE={font_size}",
            "",
            "# Height of the market-state/error strip at the bottom of the icon, in pixels (0 disables it)",
            f"STRIP_WIDTH={strip_width}",
        ]

        with open(self.config_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
