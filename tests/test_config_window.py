import pytest

from src.config_handler import ConfigHandler, MARKET_STATES
from src import config_window as config_window_module


class FakeMessageBox:
    def __init__(self):
        self.errors = []

    def showerror(self, title, message):
        self.errors.append((title, message))


class FakeColorChooser:
    def __init__(self):
        self.result = (None, None)
        self.calls = []

    def askcolor(self, color=None, **kwargs):
        self.calls.append((color, kwargs))
        return self.result


class FakeEntry:
    def __init__(self, *args, **kwargs):
        self.value = ""
        self.kwargs = kwargs

    def insert(self, index, text):
        if index != 0:
            raise ValueError("Only index 0 is supported in these tests.")
        self.value = text

    def delete(self, first, last=None):
        self.value = ""

    def get(self):
        return self.value

    def pack(self, *args, **kwargs):
        return None


class FakeSpinbox(FakeEntry):
    def set(self, text):
        self.value = str(text)


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def pack(self, *args, **kwargs):
        return None

    def grid(self, *args, **kwargs):
        return None

    def columnconfigure(self, *args, **kwargs):
        return None


class FakeButton(FakeWidget):
    def configure(self, **kwargs):
        self.kwargs.update(kwargs)


class FakeBooleanVar:
    def __init__(self, value=False):
        self._value = bool(value)

    def get(self):
        return self._value

    def set(self, value):
        self._value = bool(value)


class FakeRoot:
    def __init__(self):
        self.title_text = None
        self.resizable_value = None
        self.closed = False

    def title(self, value):
        self.title_text = value

    def resizable(self, width, height):
        self.resizable_value = (width, height)

    def protocol(self, *args, **kwargs):
        return None

    def destroy(self):
        self.closed = True

    def mainloop(self):
        return None


class FakeTtkModule:
    Frame = FakeWidget
    Entry = FakeEntry
    Spinbox = FakeSpinbox
    Combobox = FakeSpinbox
    Label = FakeWidget
    Labelframe = FakeWidget
    Button = FakeWidget
    Separator = FakeWidget
    Checkbutton = FakeWidget


class FakeTclError(Exception):
    pass


class FakeTkModule:
    Button = FakeButton
    TclError = FakeTclError

    def __init__(self):
        self.root = FakeRoot()
        self.messagebox = FakeMessageBox()
        self.ttk = FakeTtkModule()
        self.colorchooser = FakeColorChooser()

    def Tk(self):
        return self.root

    def BooleanVar(self, value=False):
        return FakeBooleanVar(value)


@pytest.fixture
def fake_tk(monkeypatch):
    """Patches the config_window module onto headless fake Tk/ttk modules."""
    fake = FakeTkModule()
    monkeypatch.setattr(config_window_module, "tk", fake)
    monkeypatch.setattr(config_window_module, "ttk", fake.ttk)
    monkeypatch.setattr(config_window_module, "messagebox", fake.messagebox)
    monkeypatch.setattr(config_window_module, "colorchooser", fake.colorchooser)
    return fake


def make_config(**overrides):
    """Builds a valid configuration dict for the window under test."""
    config = {
        "tickers": ["AMD"],
        "bg_color": (50, 50, 50),
        "error_color": (255, 40, 40),
        "state_colors": {
            state: {"positive": (1, 2, 3), "negative": (4, 5, 6), "strip": (7, 8, 9)}
            for state in MARKET_STATES
        },
        "scroll_speed_ms": 100,
        "display_ms": 2000,
        "continuous_scroll": True,
        "ticker_value_mode": "percentage",
        "show_daily_high": False,
        "show_daily_low": False,
        "high_low_pct": False,
        "font_size": 36,
        "strip_width": 2,
    }
    config.update(overrides)
    return config


def test_rgb_to_hex_round_trip():
    rgb = (10, 20, 30)

    assert ConfigHandler._rgb_to_hex(rgb) == "#0A141E"
    assert ConfigHandler._hex_to_rgb(ConfigHandler._rgb_to_hex(rgb)) == rgb


def test_config_window_collects_valid_config(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config(tickers=["amd", "msft"]))
    window.entries["tickers"].value = " amd, msft "
    window.entries["bg_color"].value = "#101112"
    window.entries["error_color"].value = "#131415"
    for state in MARKET_STATES:
        window.entries[f"{state}_positive"].value = "#010203"
        window.entries[f"{state}_negative"].value = "#040506"
        window.entries[f"{state}_strip"].value = "#070809"
    window.entries["scroll_speed_ms"].value = "320"
    window.entries["display_ms"].value = "7500"
    window.entries["font_size"].value = "40"
    window.entries["strip_width"].value = "3"
    window.entries["ticker_value_mode"].value = "Both"
    window.continuous_scroll_var.set(True)
    window.show_daily_high_var.set(True)
    window.show_daily_low_var.set(True)
    window.high_low_pct_var.set(True)

    collected = window._collect_config()

    assert collected["tickers"] == ["AMD", "MSFT"]
    assert collected["scroll_speed_ms"] == 320
    assert collected["display_ms"] == 7500
    assert collected["font_size"] == 40
    assert collected["strip_width"] == 3
    assert collected["bg_color"] == (16, 17, 18)
    assert collected["error_color"] == (19, 20, 21)
    for state in MARKET_STATES:
        assert collected["state_colors"][state] == {
            "positive": (1, 2, 3), "negative": (4, 5, 6), "strip": (7, 8, 9),
        }
    assert collected["continuous_scroll"] is True
    assert collected["ticker_value_mode"] == "both"
    assert collected["show_daily_high"] is True
    assert collected["show_daily_low"] is True
    assert collected["high_low_pct"] is True


def test_config_window_prefills_fields_from_config(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config(ticker_value_mode="price"))

    assert window.entries["tickers"].get() == "AMD"
    assert window.entries["scroll_speed_ms"].get() == "100"
    assert window.entries["display_ms"].get() == "2000"
    assert window.entries["ticker_value_mode"].get() == "Price"
    assert window.entries["bg_color"].get() == "#323232"
    assert window.entries["open_positive"].get() == "#010203"
    assert window._swatches["open_positive"].kwargs["bg"] == "#010203"


def test_config_window_rejects_unknown_ticker_value_mode(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config())
    window.entries["ticker_value_mode"].value = "Candles"

    with pytest.raises(ValueError, match="Ticker values"):
        window._collect_config()


def test_config_window_uses_expected_spinbox_increments(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config())

    # Temporal fields step by 100 ms; size fields step by 1 px
    assert window.entries["scroll_speed_ms"].kwargs["increment"] == 100
    assert window.entries["display_ms"].kwargs["increment"] == 100
    assert window.entries["font_size"].kwargs["increment"] == 1
    assert window.entries["strip_width"].kwargs["increment"] == 1


def test_pick_color_updates_entry_and_swatch(fake_tk):
    fake_tk.colorchooser.result = ((10, 20, 30), "#0a141e")
    window = config_window_module.ConfigWindow("config.cfg", make_config())

    window._pick_color("bg_color", "Background")

    assert window.entries["bg_color"].get() == "#0A141E"
    assert window._swatches["bg_color"].kwargs["bg"] == "#0A141E"


def test_pick_color_keeps_entry_when_cancelled(fake_tk):
    fake_tk.colorchooser.result = (None, None)
    window = config_window_module.ConfigWindow("config.cfg", make_config())

    window._pick_color("bg_color", "Background")

    assert window.entries["bg_color"].get() == "#323232"


def test_config_window_save_writes_file_and_calls_callback(tmp_path, fake_tk):
    config_path = tmp_path / "config.cfg"
    window = config_window_module.ConfigWindow(str(config_path), make_config(tickers=["AAPL"]),
                                               on_save=lambda cfg: cfg)
    window.entries["tickers"].value = " aapl "
    window.entries["scroll_speed_ms"].value = "180"
    window.entries["display_ms"].value = "3500"
    window.entries["font_size"].value = "44"
    window.entries["strip_width"].value = "0"
    window.entries["ticker_value_mode"].value = "Both"
    window.continuous_scroll_var.set(True)
    window.show_daily_high_var.set(True)

    callback_calls = []
    window.on_save = callback_calls.append
    window._save()

    assert config_path.exists()
    assert callback_calls
    saved = ConfigHandler(str(config_path)).load()
    assert saved["tickers"] == ["AAPL"]
    assert saved["scroll_speed_ms"] == 180
    assert saved["display_ms"] == 3500
    assert saved["continuous_scroll"] is True
    assert saved["ticker_value_mode"] == "both"
    assert saved["show_daily_high"] is True
    assert saved["show_daily_low"] is False
    assert saved["font_size"] == 44
    assert saved["strip_width"] == 0
    assert saved["state_colors"] == make_config()["state_colors"]


def test_config_window_rejects_invalid_positive_values(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config())
    window.entries["scroll_speed_ms"].value = "0"
    window.entries["display_ms"].value = "-1"

    with pytest.raises(ValueError, match="positive"):
        window._collect_config()


def test_config_window_rejects_non_positive_font_size(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config())
    window.entries["font_size"].value = "0"

    with pytest.raises(ValueError, match="Font size must be positive"):
        window._collect_config()


def test_config_window_rejects_out_of_range_strip_width(fake_tk):
    window = config_window_module.ConfigWindow("config.cfg", make_config())

    for invalid_value in ("-1", "17"):
        window.entries["strip_width"].value = invalid_value
        with pytest.raises(ValueError, match="Strip width"):
            window._collect_config()
