import pytest

from src.config_handler import ConfigHandler, MAX_TICKERS

CONFIG_CONTENT = """
TICKER=AMD,AAPL,MSFT
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
    assert config["color_positive"] == (15, 175, 80)
    assert config["color_negative"] == (235, 60, 60)
    assert config["color_error_border"] == (255, 40, 40)
    assert config["bg_open"] == (224, 255, 224)
    assert config["bg_premarket"] == (255, 255, 224)
    assert config["bg_after_hours"] == (224, 224, 255)
    assert config["bg_closed"] == (50, 50, 50)
    assert config["scroll_speed_ms"] == 500
    assert config["display_seconds"] == 8.0
    assert config["continuous_scroll"] is True


def test_load_defaults_continuous_scroll_to_false_when_missing(tmp_path):
    content = CONFIG_CONTENT.replace("CONTINUOUS_SCROLL=true\n", "")
    path = tmp_path / "config.cfg"
    path.write_text(content)

    config = ConfigHandler(str(path)).load()

    assert config["continuous_scroll"] is False


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
        "color_positive": (10, 20, 30),
        "color_negative": (40, 50, 60),
        "color_error_border": (70, 80, 90),
        "bg_open": (100, 110, 120),
        "bg_premarket": (130, 140, 150),
        "bg_after_hours": (160, 170, 180),
        "bg_closed": (190, 200, 210),
        "scroll_speed_ms": 250,
        "display_seconds": 5.5,
        "continuous_scroll": True,
    }

    ConfigHandler(str(path)).save(original)
    loaded = ConfigHandler(str(path)).load()

    assert loaded == original


def test_save_rejects_too_many_tickers(tmp_path):
    path = tmp_path / "config.cfg"
    config = {
        "tickers": [f"SYM{i}" for i in range(MAX_TICKERS + 1)],
        "color_positive": (1, 2, 3),
        "color_negative": (4, 5, 6),
        "color_error_border": (7, 8, 9),
        "bg_open": (10, 11, 12),
        "bg_premarket": (13, 14, 15),
        "bg_after_hours": (16, 17, 18),
        "bg_closed": (19, 20, 21),
        "scroll_speed_ms": 100,
        "display_seconds": 3.0,
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
