from dataclasses import dataclass
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

from src.icon_generator import IconGenerator
from src.market_api import StockData

# Tray icons are rendered at 64x64; also used as the gap width between symbols.
ICON_SIZE = 64


@dataclass
class _Segment:
    """One ticker's slice of the continuous-scroll strip, in strip-pixel coordinates."""

    symbol: str
    data: StockData
    start: int
    end: int


class ContinuousScrollGenerator:
    """
    Renders every tracked ticker into one wide strip image (e.g.
    "AMD +5.1%    INTC -2.0%    NVDA +0.1%"), separated by icon-width gaps,
    and crops a scrolling 64x64 window from it. Used by TickerIcon's
    continuous scroll mode so symbols and their values are never truncated.
    """

    def __init__(self, icon_gen: IconGenerator):
        """
        Args:
            icon_gen (IconGenerator): Supplies the font and state/change
                colors so the strip matches the rest of the tray icon.
        """
        self.icon_gen = icon_gen
        self._strip: Optional[Image.Image] = None
        self._segments: List[_Segment] = []
        self._width = 0

    @property
    def width(self) -> int:
        """
        Returns:
            int: The pixel width of the currently built strip (0 if `build` hasn't been called yet).
        """
        return self._width

    def build(self, symbols: List[str], snapshot: Dict[str, StockData]) -> None:
        """
        Renders a new scrolling strip from the given tickers/snapshot,
        replacing any strip built from a previous fetch.

        Args:
            symbols (List[str]): Ticker symbols to include, in display order.
            snapshot (Dict[str, StockData]): Latest known data, keyed by symbol.

        Returns:
            None: The rendered strip and its segment boundaries are cached
                on the instance for use by `render_frame` and `symbol_at`.
        """
        entries = [(symbol, snapshot.get(symbol, StockData(symbol=symbol))) for symbol in symbols]
        segment_images = [(symbol, data, self._render_segment(symbol, data)) for symbol, data in entries]
        segment_colors = [
            self.icon_gen.strip_color(data.state, data.has_error)
            for _, data in entries
        ]

        total_width = max(
            sum(img.width for _, _, img in segment_images) + ICON_SIZE * len(segment_images),
            ICON_SIZE,
        )

        strip = Image.new('RGB', (total_width, ICON_SIZE), color=self.icon_gen.bg_color)
        draw = ImageDraw.Draw(strip)
        segments = []
        x = 0
        for i, (symbol, data, img) in enumerate(segment_images):
            # Keep the previous symbol's strip color across the gap (wrapping),
            # so the indicator strip only changes when a new state scrolls in.
            gap_color = segment_colors[i - 1]
            if self.icon_gen.strip_width > 0:
                draw.rectangle(
                    [(x, ICON_SIZE - self.icon_gen.strip_width), (x + ICON_SIZE - 1, ICON_SIZE - 1)],
                    fill=gap_color,
                )
            x += ICON_SIZE  # leading gap, full icon width, keeps symbols visually separated
            start = x
            strip.paste(img, (x, 0))
            x += img.width
            segments.append(_Segment(symbol=symbol, data=data, start=start, end=x))

        self._strip = strip
        self._segments = segments
        self._width = total_width

    def render_frame(self, offset: int) -> Image.Image:
        """
        Crops a 64x64 frame from the strip starting at `offset`, wrapping
        around seamlessly so the strip appears to scroll endlessly.

        Args:
            offset (int): Horizontal pixel offset into the strip. May exceed
                the strip width; it wraps automatically.

        Returns:
            Image.Image: A 64x64 Pillow Image ready for pystray.
        """
        if self._strip is None or self._width == 0:
            return Image.new('RGB', (ICON_SIZE, ICON_SIZE), color=self.icon_gen.bg_color)

        start_x = offset % self._width
        end_x = start_x + ICON_SIZE
        if end_x <= self._width:
            return self._strip.crop((start_x, 0, end_x, ICON_SIZE))

        first_width = self._width - start_x
        frame = Image.new('RGB', (ICON_SIZE, ICON_SIZE))
        frame.paste(self._strip.crop((start_x, 0, self._width, ICON_SIZE)), (0, 0))
        frame.paste(self._strip.crop((0, 0, ICON_SIZE - first_width, ICON_SIZE)), (first_width, 0))
        return frame

    def symbol_at(self, offset: int) -> Optional[StockData]:
        """
        Finds the ticker whose segment covers the right (leading) edge of
        the visible window at `offset`, used to know when a new symbol has
        started scrolling into view so the tray tooltip can be refreshed.

        Args:
            offset (int): Horizontal pixel offset into the strip.

        Returns:
            Optional[StockData]: The data for the symbol currently entering
                view, or None if no strip has been built yet.
        """
        if not self._segments or self._width == 0:
            return None

        position = (offset + ICON_SIZE - 1) % self._width
        for segment in self._segments:
            if segment.start <= position < segment.end:
                return segment.data
        return None

    def next_segment_offset(self, offset: int) -> int:
        """
        Finds the offset that places the start of the segment following
        `offset` at the window's left edge, wrapping past the strip end.
        Used by the icon-click "next symbol" jump.

        Args:
            offset (int): Current horizontal pixel offset into the strip.

        Returns:
            int: The next segment's start offset, or `offset` unchanged if
                no strip has been built yet.
        """
        if not self._segments or self._width == 0:
            return offset

        position = offset % self._width
        for segment in self._segments:
            if segment.start > position:
                return segment.start
        return self._segments[0].start

    def _render_segment(self, symbol: str, data: StockData) -> Image.Image:
        """
        Draws one "SYMBOL +X.X%" segment on the static background, with the
        market-state (or error) strip along the bottom.

        Args:
            symbol (str): The ticker symbol, e.g. 'AMD'.
            data (StockData): Supplies the change percentage, market state, and error flag used for colors.

        Returns:
            Image.Image: An image exactly as wide as the rendered text (64px tall).
        """
        text = self._format_segment_text(symbol, data)
        text_color = self.icon_gen.text_color(data.state, data.change_pct)

        text_width = self.icon_gen.measure_text_width(text)
        img = Image.new('RGB', (max(text_width, 1), ICON_SIZE), color=self.icon_gen.bg_color)
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), text, font=self.icon_gen.font)
        text_height = bbox[3] - bbox[1]
        y = self.icon_gen._text_y(text_height)

        draw.text((0, y), text, fill=text_color, font=self.icon_gen.font)
        self.icon_gen.draw_strip(draw, img.width, self.icon_gen.strip_color(data.state, data.has_error))
        return img

    @staticmethod
    def _format_segment_text(symbol: str, data: StockData) -> str:
        """
        Formats one ticker's continuous-scroll label, e.g. 'AMD +5.14%'.

        Args:
            symbol (str): The ticker symbol, e.g. 'AMD'.
            data (StockData): Supplies the percentage change to display.

        Returns:
            str: The symbol followed by its signed percentage change.
        """
        return f"{symbol} {data.change_pct:+.2f}%"
