import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.config_handler import DEFAULT_FONT_SIZE, AppConfig


class IconGenerator:
    """
    Generates dynamic 64x64 PIL Images for the system tray icon,
    handling color states, typography scaling, and error borders.
    """

    @staticmethod
    def _resolve_app_icon_path() -> Path:
        """
        Locates assets/tickericon.ico in the PyInstaller bundle (frozen) or the project root (dev).

        Returns:
            Path: The resolved filesystem path to the application icon file.
        """
        if getattr(sys, 'frozen', False):
            # PyInstaller 6+ onedir places bundled data under _internal (sys._MEIPASS)
            base_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        else:
            base_dir = Path(__file__).parent.parent
        return base_dir / "assets" / "tickericon.ico"

    def __init__(self, config: AppConfig):
        """
        Args:
            config (AppConfig): Loaded app configuration with the state
                background colors and price change text colors.
        """
        # Background Colors (Pastel scheme + Dark mode for closed)
        self.bg_colors = {
            'open': config['bg_open'],
            'premarket': config['bg_premarket'],
            'after_hours': config['bg_after_hours'],
            'closed': config['bg_closed']
        }

        # Text Colors
        self.color_positive = config['color_positive']
        self.color_negative = config['color_negative']
        self.color_error_border = config['color_error_border']

        # Pre-load font to optimize rendering loop
        font_size = config.get('font_size', DEFAULT_FONT_SIZE)
        try:
            self.font = ImageFont.truetype("arialbd.ttf", font_size)
        except IOError:
            self.font = ImageFont.load_default()

        # Pre-load the static application icon, shown while idle (initializing/paused)
        try:
            self._app_icon = Image.open(self._resolve_app_icon_path()).convert('RGB').resize((64, 64))
        except (IOError, OSError):
            self._app_icon = None

    def generate_value_frame(self, change_pct: float, state: str, has_error: bool = False) -> Image.Image:
        """
        Creates the icon image based on market state and price action.
        
        Args:
            change_pct (float): Percentage change for the day.
            state (str): Current market state (e.g., 'open', 'closed').
            has_error (bool): Whether to draw the red error border.
            
        Returns:
            Image.Image: A 64x64 Pillow Image ready for pystray.
        """
        bg_color = self.bg_colors.get(state, self.bg_colors['closed'])
        text_color = self.color_positive if change_pct >= 0 else self.color_negative

        img = Image.new('RGB', (64, 64), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Format text: drop decimal for double digits to keep font large
        abs_change = abs(change_pct)
        if abs_change >= 9.95:
            text = f"{abs_change:.0f}"
        else:
            text = f"{abs_change:.1f}"

        # Calculate text bounding box to perfectly center it
        bbox = draw.textbbox((0, 0), text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (64 - text_width) / 2
        y = (64 - text_height) / 2 - 4  # Slight upward offset for visual balance

        draw.text((x, y), text, fill=text_color, font=self.font)

        # Draw 2px red border if the last update failed (scales to ~1px in tray)
        if has_error:
            draw.rectangle([(0, 0), (63, 63)], outline=self.color_error_border, width=2)

        return img

    def generate_loading_frame(self) -> Image.Image:
        """
        Creates a static placeholder icon shown before the first data fetch completes.

        Returns:
            Image.Image: A 64x64 Pillow Image ready for pystray.
        """
        bg_color = self.bg_colors['closed']
        text_color = self._contrast_text_color(bg_color)

        img = Image.new('RGB', (64, 64), color=bg_color)
        draw = ImageDraw.Draw(img)

        text = "..."
        bbox = draw.textbbox((0, 0), text, font=self.font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (64 - text_width) / 2
        y = (64 - text_height) / 2 - 4  # Slight upward offset for visual balance

        draw.text((x, y), text, fill=text_color, font=self.font)

        return img

    def generate_app_icon(self) -> Image.Image:
        """
        Returns the static application icon, shown while idle (initializing or paused).

        Returns:
            Image.Image: A 64x64 Pillow Image ready for pystray.
        """
        if self._app_icon is not None:
            return self._app_icon.copy()
        return self.generate_loading_frame()

    def generate_scroll_frame(self, symbol: str, state: str, offset: int) -> Image.Image:
        """
        Creates one frame of the right-to-left ticker symbol marquee.

        Args:
            symbol (str): The ticker symbol being scrolled, e.g. 'AMD'.
            state (str): Current market state, used for the background color.
            offset (int): Pixels the text has travelled from the right edge.

        Returns:
            Image.Image: A 64x64 Pillow Image ready for pystray.
        """
        bg_color = self.bg_colors.get(state, self.bg_colors['closed'])
        text_color = self._contrast_text_color(bg_color)

        img = Image.new('RGB', (64, 64), color=bg_color)
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), symbol, font=self.font)
        text_height = bbox[3] - bbox[1]

        x = 64 - offset
        y = (64 - text_height) / 2 - 4  # Slight upward offset for visual balance

        draw.text((x, y), symbol, fill=text_color, font=self.font)

        return img

    def measure_text_width(self, text: str) -> int:
        """
        Measures the pixel width `text` would occupy when rendered with the
        icon font, used to size the ticker symbol scroll animation.

        Args:
            text (str): The text to measure.

        Returns:
            int: The width, in pixels.
        """
        bbox = ImageDraw.Draw(Image.new('RGB', (1, 1))).textbbox((0, 0), text, font=self.font)
        return bbox[2] - bbox[0]

    @staticmethod
    def _contrast_text_color(bg_color: tuple) -> tuple:
        """
        Picks black or white text so the ticker symbol stays legible on any background.

        Args:
            bg_color (tuple): The (R, G, B) background color to contrast against.

        Returns:
            tuple: (0, 0, 0) for black or (255, 255, 255) for white text.
        """
        luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
        return (0, 0, 0) if luminance > 140 else (255, 255, 255)