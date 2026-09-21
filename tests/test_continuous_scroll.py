import pytest

from src.continuous_scroll import ContinuousScrollGenerator, ICON_SIZE
from src.icon_generator import IconGenerator
from src.market_api import StockData


@pytest.fixture
def config():
    def scheme(strip):
        return {"positive": (15, 175, 80), "negative": (235, 60, 60), "strip": strip}

    return {
        "bg_color": (50, 50, 50),
        "error_color": (255, 40, 40),
        "state_colors": {
            "open": scheme((224, 255, 224)),
            "premarket": scheme((255, 255, 224)),
            "after_hours": scheme((224, 224, 255)),
            "closed": scheme((50, 50, 50)),
        },
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

    def test_gap_strip_keeps_previous_segments_state_color(self, generator, snapshot, config):
        generator.build(["AMD", "AAPL"], snapshot)

        # Gap before AAPL follows the AMD (open) segment, so its strip stays open-colored.
        gap_before_aapl = ICON_SIZE + generator.icon_gen.measure_text_width("AMD +5.14%")
        frame = generator.render_frame(gap_before_aapl)

        assert frame.getpixel((0, ICON_SIZE - 1)) == config["state_colors"]["open"]["strip"]
        assert frame.getpixel((0, 0)) == config["bg_color"]

    def test_leading_gap_strip_wraps_to_last_segments_state_color(self, generator, snapshot, config):
        generator.build(["AMD", "AAPL"], snapshot)

        # First gap follows the wrapped-around AAPL (closed) segment.
        frame = generator.render_frame(0)

        assert frame.getpixel((0, ICON_SIZE - 1)) == config["state_colors"]["closed"]["strip"]

    def test_background_stays_static_when_all_symbols_share_a_state(self, generator, config):
        snapshot = {
            "AMD": StockData(symbol="AMD", change_pct=1.0, state="premarket"),
            "AAPL": StockData(symbol="AAPL", change_pct=-1.0, state="premarket"),
        }
        generator.build(["AMD", "AAPL"], snapshot)

        for offset in range(0, generator.width, ICON_SIZE // 2):
            frame = generator.render_frame(offset)
            assert frame.getpixel((0, 0)) == config["bg_color"]
            assert frame.getpixel((0, ICON_SIZE - 1)) == config["state_colors"]["premarket"]["strip"]

    def test_error_segment_gets_error_colored_strip(self, generator, config):
        snapshot = {
            "AMD": StockData(symbol="AMD", change_pct=1.0, state="open", has_error=True),
        }
        generator.build(["AMD"], snapshot)

        frame = generator.render_frame(ICON_SIZE)  # window fully inside the AMD segment

        assert frame.getpixel((0, ICON_SIZE - 1)) == config["error_color"]

    def test_zero_strip_width_disables_the_strip(self, config, snapshot):
        icon_gen = IconGenerator({**config, "strip_width": 0})
        generator = ContinuousScrollGenerator(icon_gen)
        generator.build(["AMD", "AAPL"], snapshot)

        for offset in range(0, generator.width, ICON_SIZE // 2):
            frame = generator.render_frame(offset)
            assert frame.getpixel((0, ICON_SIZE - 1)) == config["bg_color"]


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


class TestNextSegmentOffset:
    def test_returns_offset_unchanged_before_any_build(self, generator):
        assert generator.next_segment_offset(10) == 10

    def test_jumps_from_leading_gap_to_first_segment(self, generator, snapshot):
        generator.build(["AMD", "AAPL"], snapshot)

        assert generator.next_segment_offset(0) == ICON_SIZE

    def test_jumps_from_first_segment_to_second(self, generator, snapshot):
        generator.build(["AMD", "AAPL"], snapshot)

        amd_width = generator.icon_gen.measure_text_width("AMD +5.14%")
        expected_aapl_start = ICON_SIZE + amd_width + ICON_SIZE

        assert generator.next_segment_offset(ICON_SIZE) == expected_aapl_start

    def test_wraps_from_last_segment_to_first(self, generator, snapshot):
        generator.build(["AMD", "AAPL"], snapshot)

        assert generator.next_segment_offset(generator.width - 1) == ICON_SIZE


class TestFormatSegmentText:
    def test_percentage_mode_is_the_default(self, generator):
        data = StockData(symbol="AMD", change_pct=5.14)

        assert generator._format_segment_text("AMD", data) == "AMD +5.14%"

    def test_formats_negative_change_with_two_decimals(self, generator):
        data = StockData(symbol="AAPL", change_pct=-2.04)

        assert generator._format_segment_text("AAPL", data) == "AAPL -2.04%"

    def test_keeps_two_decimals_for_double_digit_change(self, generator):
        data = StockData(symbol="NVDA", change_pct=12.34)

        assert generator._format_segment_text("NVDA", data) == "NVDA +12.34%"

    def test_price_mode_shows_only_the_price(self, icon_gen):
        generator = ContinuousScrollGenerator(icon_gen, {"ticker_value_mode": "price"})
        data = StockData(symbol="AMD", price=123.456, change_pct=5.14)

        assert generator._format_segment_text("AMD", data) == "AMD 123.46"

    def test_both_mode_shows_price_then_percentage(self, icon_gen):
        generator = ContinuousScrollGenerator(icon_gen, {"ticker_value_mode": "both"})
        data = StockData(symbol="AMD", price=123.45, change_pct=5.14)

        assert generator._format_segment_text("AMD", data) == "AMD 123.45 +5.14%"

    def test_unknown_mode_falls_back_to_percentage(self, icon_gen):
        generator = ContinuousScrollGenerator(icon_gen, {"ticker_value_mode": "candles"})
        data = StockData(symbol="AMD", change_pct=5.14)

        assert generator._format_segment_text("AMD", data) == "AMD +5.14%"

    def test_daily_high_and_low_use_arrows(self, icon_gen):
        generator = ContinuousScrollGenerator(
            icon_gen, {"show_daily_high": True, "show_daily_low": True},
        )
        data = StockData(symbol="AMD", change_pct=5.14, day_high=125.0, day_low=119.5)

        assert generator._format_segment_text("AMD", data) == "AMD +5.14% ↑125.00 ↓119.50"

    def test_daily_high_and_low_are_independent_toggles(self, icon_gen):
        generator = ContinuousScrollGenerator(icon_gen, {"show_daily_low": True})
        data = StockData(symbol="AMD", change_pct=5.14, day_high=125.0, day_low=119.5)

        assert generator._format_segment_text("AMD", data) == "AMD +5.14% ↓119.50"

    def test_high_low_pct_appends_change_vs_previous_close(self, icon_gen):
        generator = ContinuousScrollGenerator(
            icon_gen,
            {"show_daily_high": True, "show_daily_low": True, "high_low_pct": True},
        )
        data = StockData(
            symbol="AMD", change_pct=5.14, day_high=110.0, day_low=95.0, prev_close=100.0,
        )

        assert generator._format_segment_text("AMD", data) == (
            "AMD +5.14% ↑110.00 (+10.00%) ↓95.00 (-5.00%)"
        )

    def test_high_low_pct_skipped_without_a_previous_close(self, icon_gen):
        generator = ContinuousScrollGenerator(
            icon_gen, {"show_daily_high": True, "high_low_pct": True},
        )
        data = StockData(symbol="AMD", change_pct=5.14, day_high=110.0, prev_close=0.0)

        assert generator._format_segment_text("AMD", data) == "AMD +5.14% ↑110.00"
