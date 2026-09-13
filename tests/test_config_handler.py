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


@pytest.mark.parametrize("hex_value, expected", [
    ("#0FAF50", (15, 175, 80)),
    ("0FAF50", (15, 175, 80)),
    ("#FFFFFF", (255, 255, 255)),
    ("#000000", (0, 0, 0)),
])
def test_hex_to_rgb(hex_value, expected):
    assert ConfigHandler._hex_to_rgb(hex_value) == expected
