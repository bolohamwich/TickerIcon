import pytest

from src.config_handler import ConfigHandler, MARKET_STATES, MAX_TICKERS

CONFIG_CONTENT = """
TICKER=AMD,AAPL,MSFT
COLOR_BACKGROUND=#323232
COLOR_ERROR=#FF2828
COLOR_OPEN_POSITIVE=#0FAF50
COLOR_OPEN_NEGATIVE=#EB3C3C
COLOR_OPEN_STRIP=#E0FFE0
COLOR_PREMARKET_POSITIVE=#10AF50
COLOR_PREMARKET_NEGATIVE=#EC3C3C
COLOR_PREMARKET_STRIP=#FFFFE0
COLOR_AFTER_HOURS_POSITIVE=#11AF50
COLOR_AFTER_HOURS_NEGATIVE=#ED3C3C
COLOR_AFTER_HOURS_STRIP=#E0E0FF
COLOR_CLOSED_POSITIVE=#12AF50
COLOR_CLOSED_NEGATIVE=#EE3C3C
COLOR_CLOSED_STRIP=#323232
SCROLL_SPEED_MS=500
DISPLAY_MS=8000
CONTINUOUS_SCROLL=true
TICKER_VALUE_MODE=both
SHOW_DAILY_HIGH=true
SHOW_DAILY_LOW=true
HIGH_LOW_PCT=true
FONT_SIZE=36
STRIP_WIDTH=2
"""

LEGACY_CONFIG_CONTENT = """
TICKER=AMD,AAPL
COLOR_POSITIVE=#0FAF50
COLOR_NEGATIVE=#EB3C3C
COLOR_ERROR_BORDER=#FF2828
COLOR_OPEN=#E0FFE0
COLOR_PREMARKET=#FFFFE0
COLOR_AFTER_HOURS=#E0E0FF
COLOR_CLOSED=#323232
SCROLL_SPEED_MS=500
DISPLAY_SECONDS=8
CONTINUOUS_SCROLL=true
"""


@pytest.fixture
def config_file(tmp_path):
    """Writes a valid config.cfg to a temp dir and returns its path."""
    path = tmp_path / "config.cfg"
    path.write_text(CONFIG_CONTENT)
    return str(path)


def test_load_parses_tickers_and_colors(config_file):
    config = ConfigHandler(config_file).load()

    assert config["tickers"] == ["AMD", "AAPL", "MSFT"]
    assert config["bg_color"] == (50, 50, 50)
    assert config["error_color"] == (255, 40, 40)
    assert config["state_colors"]["open"] == {
        "positive": (15, 175, 80), "negative": (235, 60, 60), "strip": (224, 255, 224),
    }
    assert config["state_colors"]["premarket"] == {
        "positive": (16, 175, 80), "negative": (236, 60, 60), "strip": (255, 255, 224),
    }
    assert config["state_colors"]["after_hours"] == {
        "positive": (17, 175, 80), "negative": (237, 60, 60), "strip": (224, 224, 255),
    }
    assert config["state_colors"]["closed"] == {
        "positive": (18, 175, 80), "negative": (238, 60, 60), "strip": (50, 50, 50),
    }
    assert config["scroll_speed_ms"] == 500
    assert config["display_ms"] == 8000
    assert config["continuous_scroll"] is True
    assert config["ticker_value_mode"] == "both"
    assert config["show_daily_high"] is True
    assert config["show_daily_low"] is True
    assert config["high_low_pct"] is True
    assert config["font_size"] == 36
    assert config["strip_width"] == 2


def test_load_accepts_legacy_color_and_display_keys(tmp_path):
    path = tmp_path / "config.cfg"
    path.write_text(LEGACY_CONFIG_CONTENT)

    config = ConfigHandler(str(path)).load()

    assert config["bg_color"] == (50, 50, 50)  # from COLOR_CLOSED
    assert config["error_color"] == (255, 40, 40)  # from COLOR_ERROR_BORDER
    for state in MARKET_STATES:
        assert config["state_colors"][state]["positive"] == (15, 175, 80)
        assert config["state_colors"][state]["negative"] == (235, 60, 60)
    assert config["state_colors"]["open"]["strip"] == (224, 255, 224)  # from COLOR_OPEN
    assert config["display_ms"] == 8000  # from DISPLAY_SECONDS=8


def test_load_falls_back_to_defaults_when_no_color_keys_exist(tmp_path):
    path = tmp_path / "config.cfg"
    path.write_text("TICKER=AMD\nSCROLL_SPEED_MS=500\nDISPLAY_MS=8000\n")

    config = ConfigHandler(str(path)).load()

    assert config["bg_color"] == (50, 50, 50)
    assert config["error_color"] == (255, 40, 40)
    assert config["state_colors"]["premarket"]["strip"] == (255, 255, 224)


def test_load_defaults_continuous_scroll_to_true_when_missing(tmp_path):
    content = CONFIG_CONTENT.replace("CONTINUOUS_SCROLL=true\n", "")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["continuous_scroll"] is True


def test_load_parses_continuous_scroll_false(tmp_path):
    content = CONFIG_CONTENT.replace("CONTINUOUS_SCROLL=true", "CONTINUOUS_SCROLL=false")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["continuous_scroll"] is False


def test_load_rejects_non_positive_scroll_speed(tmp_path):
    content = CONFIG_CONTENT.replace("SCROLL_SPEED_MS=500", "SCROLL_SPEED_MS=0")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    with pytest.raises(ValueError, match="SCROLL_SPEED_MS"):
        ConfigHandler(str(path)).load()


def test_load_rejects_non_positive_display_ms(tmp_path):
    content = CONFIG_CONTENT.replace("DISPLAY_MS=8000", "DISPLAY_MS=0")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    with pytest.raises(ValueError, match="DISPLAY_MS"):
        ConfigHandler(str(path)).load()


def test_load_defaults_ticker_display_options_when_missing(tmp_path):
    content = CONFIG_CONTENT
    for line in ("TICKER_VALUE_MODE=both\n", "SHOW_DAILY_HIGH=true\n",
                 "SHOW_DAILY_LOW=true\n", "HIGH_LOW_PCT=true\n"):
        content = content.replace(line, "")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["ticker_value_mode"] == "percentage"
    assert config["show_daily_high"] is False
    assert config["show_daily_low"] is False
    assert config["high_low_pct"] is False


def test_load_rejects_unknown_ticker_value_mode(tmp_path):
    content = CONFIG_CONTENT.replace("TICKER_VALUE_MODE=both", "TICKER_VALUE_MODE=candles")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    with pytest.raises(ValueError, match="TICKER_VALUE_MODE"):
        ConfigHandler(str(path)).load()


def test_save_rejects_unknown_ticker_value_mode(tmp_path):
    path = tmp_path / "config.cfg"
    config = {
        "tickers": ["AMD"],
        "bg_color": (10, 20, 30),
        "error_color": (40, 50, 60),
        "state_colors": {
            state: {"positive": (1, 2, 3), "negative": (4, 5, 6), "strip": (7, 8, 9)}
            for state in MARKET_STATES
        },
        "scroll_speed_ms": 250,
        "display_ms": 5500,
        "ticker_value_mode": "candles",
    }

    with pytest.raises(ValueError, match="TICKER_VALUE_MODE"):
        ConfigHandler(str(path)).save(config)


def test_load_defaults_font_size_when_missing(tmp_path):
    content = CONFIG_CONTENT.replace("FONT_SIZE=36\n", "")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["font_size"] == 36


def test_load_parses_custom_font_size(tmp_path):
    content = CONFIG_CONTENT.replace("FONT_SIZE=36", "FONT_SIZE=44")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["font_size"] == 44


def test_load_rejects_non_positive_font_size(tmp_path):
    content = CONFIG_CONTENT.replace("FONT_SIZE=36", "FONT_SIZE=0")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    with pytest.raises(ValueError, match="FONT_SIZE"):
        ConfigHandler(str(path)).load()


def test_load_defaults_strip_width_when_missing(tmp_path):
    content = CONFIG_CONTENT.replace("STRIP_WIDTH=2\n", "")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["strip_width"] == 2


def test_load_parses_custom_strip_width(tmp_path):
    content = CONFIG_CONTENT.replace("STRIP_WIDTH=2", "STRIP_WIDTH=4")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["strip_width"] == 4


def test_load_allows_zero_strip_width(tmp_path):
    content = CONFIG_CONTENT.replace("STRIP_WIDTH=2", "STRIP_WIDTH=0")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["strip_width"] == 0


def test_load_rejects_negative_strip_width(tmp_path):
    content = CONFIG_CONTENT.replace("STRIP_WIDTH=2", "STRIP_WIDTH=-1")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    with pytest.raises(ValueError, match="STRIP_WIDTH"):
        ConfigHandler(str(path)).load()


def test_load_rejects_oversized_strip_width(tmp_path):
    content = CONFIG_CONTENT.replace("STRIP_WIDTH=2", "STRIP_WIDTH=17")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    with pytest.raises(ValueError, match="STRIP_WIDTH"):
        ConfigHandler(str(path)).load()


def test_load_strips_whitespace_and_uppercases_tickers(tmp_path):
    content = CONFIG_CONTENT.replace("TICKER=AMD,AAPL,MSFT", "TICKER= amd , aapl ,msft ")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["tickers"] == ["AMD", "AAPL", "MSFT"]


def test_load_ignores_empty_ticker_entries(tmp_path):
    content = CONFIG_CONTENT.replace("TICKER=AMD,AAPL,MSFT", "TICKER=AMD,,AAPL,")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["tickers"] == ["AMD", "AAPL"]


def test_load_caps_ticker_list_to_max_tickers(tmp_path):
    too_many = ",".join(f"SYM{i}" for i in range(MAX_TICKERS + 5))
    content = CONFIG_CONTENT.replace("TICKER=AMD,AAPL,MSFT", f"TICKER={too_many}")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert len(config["tickers"]) == MAX_TICKERS
    assert config["tickers"] == [f"SYM{i}" for i in range(MAX_TICKERS)]


def test_save_round_trips_config(tmp_path):
    path = tmp_path / "config.cfg"
    original = {
        "tickers": ["AMD", "MSFT"],
        "bg_color": (10, 20, 30),
        "error_color": (40, 50, 60),
        "state_colors": {
            "open": {"positive": (1, 2, 3), "negative": (4, 5, 6), "strip": (7, 8, 9)},
            "premarket": {"positive": (11, 12, 13), "negative": (14, 15, 16), "strip": (17, 18, 19)},
            "after_hours": {"positive": (21, 22, 23), "negative": (24, 25, 26), "strip": (27, 28, 29)},
            "closed": {"positive": (31, 32, 33), "negative": (34, 35, 36), "strip": (37, 38, 39)},
        },
        "scroll_speed_ms": 250,
        "display_ms": 5500,
        "continuous_scroll": True,
        "ticker_value_mode": "both",
        "show_daily_high": True,
        "show_daily_low": False,
        "high_low_pct": True,
        "font_size": 40,
        "strip_width": 3,
    }

    ConfigHandler(str(path)).save(original)
    loaded = ConfigHandler(str(path)).load()

    assert loaded == original


def test_save_rejects_missing_state_scheme(tmp_path):
    path = tmp_path / "config.cfg"
    config = {
        "tickers": ["AMD"],
        "bg_color": (10, 20, 30),
        "error_color": (40, 50, 60),
        "state_colors": {
            "open": {"positive": (1, 2, 3), "negative": (4, 5, 6), "strip": (7, 8, 9)},
        },
        "scroll_speed_ms": 250,
        "display_ms": 5500,
    }

    with pytest.raises(ValueError, match="premarket"):
        ConfigHandler(str(path)).save(config)


def test_save_rejects_too_many_tickers(tmp_path):
    path = tmp_path / "config.cfg"
    config = {
        "tickers": [f"SYM{i}" for i in range(MAX_TICKERS + 1)],
        "bg_color": (10, 20, 30),
        "error_color": (40, 50, 60),
        "state_colors": {
            state: {"positive": (1, 2, 3), "negative": (4, 5, 6), "strip": (7, 8, 9)}
            for state in MARKET_STATES
        },
        "scroll_speed_ms": 100,
        "display_ms": 3000,
    }

    with pytest.raises(ValueError, match="MAX_TICKERS"):
        ConfigHandler(str(path)).save(config)


@pytest.mark.parametrize("hex_value, expected", [
    ("#0FAF50", (15, 175, 80)),
    ("0FAF50", (15, 175, 80)),
    ("#FFFFFF", (255, 255, 255)),
    ("#000000", (0, 0, 0)),
])
def test_hex_to_rgb(hex_value, expected):
    assert ConfigHandler._hex_to_rgb(hex_value) == expected
