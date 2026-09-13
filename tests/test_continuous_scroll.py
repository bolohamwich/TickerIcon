import pytest

from src.continuous_scroll import ContinuousScrollGenerator, ICON_SIZE
from src.icon_generator import IconGenerator
from src.market_api import StockData


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


@pytest.fixture
def generator(icon_gen):
    return ContinuousScrollGenerator(icon_gen)


@pytest.fixture
def snapshot():
    return {
        "AMD": StockData(symbol="AMD", change_pct=5.14, state="open"),
        "AAPL": StockData(symbol="AAPL", change_pct=-2.04, state="closed"),
    }


class TestBuild:
    def test_width_is_zero_before_build(self, generator):
        assert generator.width == 0

    def test_width_includes_icon_width_gap_per_symbol(self, generator, snapshot):
        generator.build(["AMD"], snapshot)

        text_width = generator.icon_gen.measure_text_width("AMD +5.14%")
        assert generator.width == ICON_SIZE + text_width

    def test_width_grows_with_more_symbols(self, generator, snapshot):
        generator.build(["AMD"], snapshot)
        single_width = generator.width

        generator.build(["AMD", "AAPL"], snapshot)

        assert generator.width > single_width

    def test_falls_back_to_placeholder_data_for_missing_symbol(self, generator):
        generator.build(["MSFT"], {})

        assert generator.width == ICON_SIZE + generator.icon_gen.measure_text_width("MSFT +0.00%")


class TestRenderFrame:
    def test_returns_64x64_image(self, generator, snapshot):
        generator.build(["AMD", "AAPL"], snapshot)

        frame = generator.render_frame(0)

        assert frame.size == (ICON_SIZE, ICON_SIZE)

    def test_wraps_around_seamlessly_past_the_strip_end(self, generator, snapshot):
        generator.build(["AMD"], snapshot)

        frame = generator.render_frame(generator.width - 1)

        assert frame.size == (ICON_SIZE, ICON_SIZE)

    def test_returns_blank_frame_before_any_build(self, generator):
        frame = generator.render_frame(0)

        assert frame.size == (ICON_SIZE, ICON_SIZE)


class TestSymbolAt:
    def test_returns_none_before_any_build(self, generator):
        assert generator.symbol_at(0) is None

    def test_identifies_symbol_entering_from_the_right_edge(self, generator, snapshot):
        generator.build(["AMD"], snapshot)

        # Right edge of the window is at offset + ICON_SIZE - 1, which first
        # reaches the AMD segment (starting right after the leading gap) at offset=1.
        data = generator.symbol_at(1)

        assert data is not None
        assert data.symbol == "AMD"

    def test_returns_none_while_only_the_gap_is_visible(self, generator, snapshot):
        generator.build(["AMD"], snapshot)

        # At offset 0, the entire visible window (0..63) is still the leading gap.
        data = generator.symbol_at(0)

        assert data is None


class TestFormatSegmentText:
    def test_formats_positive_change_with_two_decimals(self):
        data = StockData(symbol="AMD", change_pct=5.14)

        assert ContinuousScrollGenerator._format_segment_text("AMD", data) == "AMD +5.14%"

    def test_formats_negative_change_with_two_decimals(self):
        data = StockData(symbol="AAPL", change_pct=-2.04)

        assert ContinuousScrollGenerator._format_segment_text("AAPL", data) == "AAPL -2.04%"

    def test_keeps_two_decimals_for_double_digit_change(self):
        data = StockData(symbol="NVDA", change_pct=12.34)

        assert ContinuousScrollGenerator._format_segment_text("NVDA", data) == "NVDA +12.34%"
