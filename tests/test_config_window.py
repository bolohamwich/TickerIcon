import pytest

from src.config_handler import ConfigHandler
from src import config_window as config_window_module


class FakeMessageBox:
    def __init__(self):
        self.errors = []

    def showerror(self, title, message):
        self.errors.append((title, message))


class FakeEntry:
    def __init__(self, *args, **kwargs):
        self.value = ""
        self.kwargs = kwargs

    def insert(self, index, text):
        if index != 0:
            raise ValueError("Only index 0 is supported in these tests.")
        self.value = text

    def get(self):
        return self.value

    def pack(self, *args, **kwargs):
        return None


class FakeWidget:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def pack(self, *args, **kwargs):
        return None


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
        self.geometry_value = None
        self.resizable_value = None
        self.closed = False

    def title(self, value):
        self.title_text = value

    def geometry(self, value):
        self.geometry_value = value

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
    Label = FakeWidget
    Button = FakeWidget
    Separator = FakeWidget
    Checkbutton = FakeWidget


class FakeTkModule:
    def __init__(self):
        self.root = FakeRoot()
        self.messagebox = FakeMessageBox()
        self.ttk = FakeTtkModule()

    def Tk(self):
        return self.root

    def BooleanVar(self, value=False):
        return FakeBooleanVar(value)


def test_rgb_to_hex_round_trip():
    rgb = (10, 20, 30)

    assert ConfigHandler._rgb_to_hex(rgb) == "#0A141E"
    assert ConfigHandler._hex_to_rgb(ConfigHandler._rgb_to_hex(rgb)) == rgb


def test_config_window_collects_valid_config(monkeypatch):
    fake_tk = FakeTkModule()
    monkeypatch.setattr(config_window_module, "tk", fake_tk)
    monkeypatch.setattr(config_window_module, "ttk", fake_tk.ttk)
    monkeypatch.setattr(config_window_module, "messagebox", fake_tk.messagebox)

    config = {
        "tickers": ["amd", "msft"],
        "color_positive": (10, 20, 30),
        "color_negative": (40, 50, 60),
        "color_error_border": (70, 80, 90),
        "bg_open": (100, 110, 120),
        "bg_premarket": (130, 140, 150),
        "bg_after_hours": (160, 170, 180),
        "bg_closed": (190, 200, 210),
        "scroll_speed_ms": 250,
        "display_seconds": 5.5,
    }

    window = config_window_module.ConfigWindow("config.cfg", config)
    window.entries["tickers"].value = " amd, msft "
    window.entries["color_positive"].value = "#010203"
    window.entries["color_negative"].value = "#040506"
    window.entries["color_error_border"].value = "#070809"
    window.entries["bg_open"].value = "#0A0B0C"
    window.entries["bg_premarket"].value = "#0D0E0F"
    window.entries["bg_after_hours"].value = "#101112"
    window.entries["bg_closed"].value = "#131415"
    window.entries["scroll_speed_ms"].value = "320"
    window.entries["display_seconds"].value = "7.5"
    window.continuous_scroll_var.set(True)

    collected = window._collect_config()

    assert collected["tickers"] == ["AMD", "MSFT"]
    assert collected["scroll_speed_ms"] == 320
    assert collected["display_seconds"] == 7.5
    assert collected["color_positive"] == (1, 2, 3)
    assert collected["bg_closed"] == (19, 20, 21)
    assert collected["continuous_scroll"] is True


def test_config_window_save_writes_file_and_calls_callback(tmp_path, monkeypatch):
    fake_tk = FakeTkModule()
    monkeypatch.setattr(config_window_module, "tk", fake_tk)
    monkeypatch.setattr(config_window_module, "ttk", fake_tk.ttk)
    monkeypatch.setattr(config_window_module, "messagebox", fake_tk.messagebox)

    config_path = tmp_path / "config.cfg"
    original = {
        "tickers": ["AAPL"],
        "color_positive": (1, 2, 3),
        "color_negative": (4, 5, 6),
        "color_error_border": (7, 8, 9),
        "bg_open": (10, 11, 12),
        "bg_premarket": (13, 14, 15),
        "bg_after_hours": (16, 17, 18),
        "bg_closed": (19, 20, 21),
        "scroll_speed_ms": 150,
        "display_seconds": 2.5,
    }

    window = config_window_module.ConfigWindow(str(config_path), original, on_save=lambda cfg: cfg)
    window.entries["tickers"].value = " aapl "
    window.entries["color_positive"].value = "#010203"
    window.entries["color_negative"].value = "#040506"
    window.entries["color_error_border"].value = "#070809"
    window.entries["bg_open"].value = "#0A0B0C"
    window.entries["bg_premarket"].value = "#0D0E0F"
    window.entries["bg_after_hours"].value = "#101112"
    window.entries["bg_closed"].value = "#131415"
    window.entries["scroll_speed_ms"].value = "180"
    window.entries["display_seconds"].value = "3.5"
    window.continuous_scroll_var.set(True)

    callback_calls = []
    window.on_save = callback_calls.append
    window._save()

    assert config_path.exists()
    assert callback_calls
    saved = ConfigHandler(str(config_path)).load()
    assert saved["tickers"] == ["AAPL"]
    assert saved["scroll_speed_ms"] == 180
    assert saved["display_seconds"] == 3.5
    assert saved["continuous_scroll"] is True


def test_config_window_rejects_invalid_positive_values(monkeypatch):
    fake_tk = FakeTkModule()
    monkeypatch.setattr(config_window_module, "tk", fake_tk)
    monkeypatch.setattr(config_window_module, "ttk", fake_tk.ttk)
    monkeypatch.setattr(config_window_module, "messagebox", fake_tk.messagebox)

    window = config_window_module.ConfigWindow("config.cfg", {
        "tickers": ["AMD"],
        "color_positive": (1, 2, 3),
        "color_negative": (4, 5, 6),
        "color_error_border": (7, 8, 9),
        "bg_open": (10, 11, 12),
        "bg_premarket": (13, 14, 15),
        "bg_after_hours": (16, 17, 18),
        "bg_closed": (19, 20, 21),
        "scroll_speed_ms": 100,
        "display_seconds": 2.0,
    })

    window.entries["tickers"].value = "AMD"
    window.entries["color_positive"].value = "#010203"
    window.entries["color_negative"].value = "#040506"
    window.entries["color_error_border"].value = "#070809"
    window.entries["bg_open"].value = "#0A0B0C"
    window.entries["bg_premarket"].value = "#0D0E0F"
    window.entries["bg_after_hours"].value = "#101112"
    window.entries["bg_closed"].value = "#131415"
    window.entries["scroll_speed_ms"].value = "0"
    window.entries["display_seconds"].value = "-1"

    with pytest.raises(ValueError, match="positive"):
        window._collect_config()
