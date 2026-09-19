import pytest

from src.icon_generator import IconGenerator


@pytest.fixture
def config():
    return {
        "bg_open": (224, 255, 224),
        "bg_premarket": (255, 255, 224),
        "bg_after_hours": (224, 224, 255),
        "bg_closed": (50, 50, 50),
        "color_positive": (15, 175, 80),
        "color_negative": (235, 60, 60),
        "color_error_border": (255, 40, 40),
    }


@pytest.fixture
def icon_gen(config):
    return IconGenerator(config)


class TestFontSize:
    def test_uses_configured_font_size(self, config, monkeypatch):
        sizes = []
        monkeypatch.setattr(
            "src.icon_generator.ImageFont.truetype",
            lambda path, size: sizes.append(size),
        )
        IconGenerator({**config, "font_size": 44})
        assert sizes == [44]

    def test_defaults_font_size_when_missing(self, config, monkeypatch):
        sizes = []
        monkeypatch.setattr(
            "src.icon_generator.ImageFont.truetype",
            lambda path, size: sizes.append(size),
        )
        IconGenerator(config)
        assert sizes == [36]


class TestGenerateValueFrame:
    def test_returns_64x64_image(self, icon_gen):
        image = icon_gen.generate_value_frame(2.5, "open")
        assert image.size == (64, 64)

    def test_background_is_static_regardless_of_state(self, icon_gen, config):
        for state in ("open", "premarket", "after_hours", "closed"):
            image = icon_gen.generate_value_frame(2.5, state)
            assert image.getpixel((0, 0)) == config["bg_closed"]

    def test_bottom_strip_uses_state_color(self, icon_gen, config):
        image = icon_gen.generate_value_frame(2.5, "open")
        assert image.getpixel((0, 63)) == config["bg_open"]
        assert image.getpixel((63, 62)) == config["bg_open"]

    def test_strip_falls_back_to_closed_color_for_unknown_state(self, icon_gen, config):
        image = icon_gen.generate_value_frame(2.5, "some_unknown_state")
        assert image.getpixel((0, 63)) == config["bg_closed"]

    def test_strip_uses_error_color_when_has_error(self, icon_gen, config):
        image = icon_gen.generate_value_frame(1.0, "open", has_error=True)
        assert image.getpixel((0, 63)) == config["color_error_border"]
        assert image.getpixel((0, 0)) == config["bg_closed"]

    def test_strip_uses_state_color_when_no_error(self, icon_gen, config):
        image = icon_gen.generate_value_frame(1.0, "open", has_error=False)
        assert image.getpixel((0, 63)) == config["bg_open"]

    def test_strip_height_matches_configured_width(self, config):
        icon_gen = IconGenerator({**config, "strip_width": 4})
        image = icon_gen.generate_value_frame(1.0, "open")
        assert image.getpixel((0, 60)) == config["bg_open"]
        assert image.getpixel((0, 59)) == config["bg_closed"]

    def test_zero_strip_width_disables_the_strip(self, config):
        icon_gen = IconGenerator({**config, "strip_width": 0})
        image = icon_gen.generate_value_frame(1.0, "open", has_error=True)
        assert image.getpixel((0, 63)) == config["bg_closed"]


class TestGenerateAppIcon:
    def test_returns_64x64_image(self, icon_gen):
        image = icon_gen.generate_app_icon()
        assert image.size == (64, 64)

    def test_falls_back_to_loading_frame_when_icon_file_missing(self, icon_gen, config):
        icon_gen._app_icon = None
        image = icon_gen.generate_app_icon()
        assert image.getpixel((0, 0)) == config["bg_closed"]

    def test_resolve_path_uses_meipass_when_frozen(self, monkeypatch):
        import sys
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", "/bundle/_internal", raising=False)

        path = IconGenerator._resolve_app_icon_path()

        assert path.as_posix() == "/bundle/_internal/assets/tickericon.ico"

    def test_resolve_path_uses_project_root_in_dev(self):
        path = IconGenerator._resolve_app_icon_path()

        assert path.name == "tickericon.ico"
        assert path.parent.name == "assets"
        assert path.exists()


class TestGenerateLoadingFrame:
    def test_returns_64x64_image(self, icon_gen):
        image = icon_gen.generate_loading_frame()
        assert image.size == (64, 64)

    def test_uses_closed_background_color(self, icon_gen, config):
        image = icon_gen.generate_loading_frame()
        assert image.getpixel((0, 0)) == config["bg_closed"]

    def test_draws_readable_placeholder_text(self, icon_gen, config):
        image = icon_gen.generate_loading_frame()
        pixels = list(image.getdata())
        assert config["bg_closed"] in pixels
        assert any(pixel != config["bg_closed"] for pixel in pixels)


class TestGenerateScrollFrame:
    def test_returns_64x64_image(self, icon_gen):
        image = icon_gen.generate_scroll_frame("AMD", "closed", offset=10)
        assert image.size == (64, 64)

    def test_background_is_static_regardless_of_state(self, icon_gen, config):
        image = icon_gen.generate_scroll_frame("AMD", "premarket", offset=0)
        assert image.getpixel((0, 0)) == config["bg_closed"]

    def test_bottom_strip_uses_state_color(self, icon_gen, config):
        image = icon_gen.generate_scroll_frame("AMD", "premarket", offset=0)
        assert image.getpixel((0, 63)) == config["bg_premarket"]

    def test_strip_falls_back_to_closed_color_for_unknown_state(self, icon_gen, config):
        image = icon_gen.generate_scroll_frame("AMD", "some_unknown_state", offset=0)
        assert image.getpixel((0, 63)) == config["bg_closed"]


class TestMeasureTextWidth:
    def test_returns_positive_width_for_nonempty_text(self, icon_gen):
        assert icon_gen.measure_text_width("AMD") > 0

    def test_scales_with_text_length(self, icon_gen):
        assert icon_gen.measure_text_width("AMD") < icon_gen.measure_text_width("AMDAMD")


class TestContrastTextColor:
    @pytest.mark.parametrize("bg_color, expected", [
        ((255, 255, 255), (0, 0, 0)),
        ((0, 0, 0), (255, 255, 255)),
        ((224, 255, 224), (0, 0, 0)),
        ((50, 50, 50), (255, 255, 255)),
    ])
    def test_picks_readable_text_color(self, bg_color, expected):
        assert IconGenerator._contrast_text_color(bg_color) == expected


class TestStripColor:
    def test_returns_state_color(self, icon_gen, config):
        assert icon_gen.strip_color("open") == config["bg_open"]

    def test_error_takes_precedence_over_state(self, icon_gen, config):
        assert icon_gen.strip_color("open", has_error=True) == config["color_error_border"]

    def test_falls_back_to_closed_color_for_unknown_state(self, icon_gen, config):
        assert icon_gen.strip_color("nope") == config["bg_closed"]


class TestTextY:
    def test_text_moves_up_by_strip_width(self, config):
        default_gen = IconGenerator({**config, "strip_width": 2})
        wide_gen = IconGenerator({**config, "strip_width": 6})

        assert wide_gen._text_y(20) == default_gen._text_y(20) - 4

    def test_zero_strip_width_keeps_centered_offset(self, config):
        icon_gen = IconGenerator({**config, "strip_width": 0})

        assert icon_gen._text_y(20) == (64 - 20) / 2 - 4
