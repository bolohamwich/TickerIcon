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

        total_width = max(
            sum(img.width for _, _, img in segment_images) + ICON_SIZE * len(segment_images),
            ICON_SIZE,
        )

        strip = Image.new('RGB', (total_width, ICON_SIZE), color=self.icon_gen.bg_colors['closed'])
        segments = []
        x = 0
        for symbol, data, img in segment_images:
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
            return Image.new('RGB', (ICON_SIZE, ICON_SIZE), color=self.icon_gen.bg_colors['closed'])

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

    def _render_segment(self, symbol: str, data: StockData) -> Image.Image:
        """
        Draws one "SYMBOL +X.X%" segment against its market-state background.

        Args:
            symbol (str): The ticker symbol, e.g. 'AMD'.
            data (StockData): Supplies the change percentage and market state used for colors.

        Returns:
            Image.Image: An image exactly as wide as the rendered text (64px tall).
        """
        text = self._format_segment_text(symbol, data)
        bg_color = self.icon_gen.bg_colors.get(data.state, self.icon_gen.bg_colors['closed'])
        text_color = self.icon_gen.color_positive if data.change_pct >= 0 else self.icon_gen.color_negative

        text_width = self.icon_gen.measure_text_width(text)
        img = Image.new('RGB', (max(text_width, 1), ICON_SIZE), color=bg_color)
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), text, font=self.icon_gen.font)
        text_height = bbox[3] - bbox[1]
        y = (ICON_SIZE - text_height) / 2 - 4  # Slight upward offset for visual balance

        draw.text((0, y), text, fill=text_color, font=self.icon_gen.font)
        if data.has_error:
            draw.rectangle([(0, 0), (img.width - 1, ICON_SIZE - 1)], outline=self.icon_gen.color_error_border, width=2)
        return img

    @staticmethod
    def _format_segment_text(symbol: str, data: StockData) -> str:
        """
        Formats one ticker's continuous-scroll label, e.g. 'AMD +5.1%'.

        Args:
            symbol (str): The ticker symbol, e.g. 'AMD'.
            data (StockData): Supplies the percentage change to display.

        Returns:
            str: The symbol followed by its signed percentage change.
        """
        abs_change = abs(data.change_pct)
        if abs_change >= 9.95:
            value_text = f"{data.change_pct:+.0f}%"
        else:
            value_text = f"{data.change_pct:+.1f}%"
        return f"{symbol} {value_text}"
