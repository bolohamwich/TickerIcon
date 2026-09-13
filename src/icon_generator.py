from PIL import Image, ImageDraw, ImageFont


class IconGenerator:
    """
    Generates dynamic 64x64 PIL Images for the system tray icon,
    handling color states, typography scaling, and error borders.
    """

    def __init__(self):
        # Background Colors (Pastel scheme + Dark mode for closed)
        self.bg_colors = {
            'open': (224, 255, 224),         # Light green
            'premarket': (255, 255, 224),    # Light yellow
            'after_hours': (224, 224, 255),  # Light blue
            'closed': (50, 50, 50)           # Dark grey
        }
        
        # Text Colors
        self.color_positive = (15, 175, 80)  # Vibrant Green
        self.color_negative = (235, 60, 60)  # Vibrant Red
        self.color_error_border = (255, 40, 40)

        # Pre-load font to optimize rendering loop
        try:
            self.font = ImageFont.truetype("arialbd.ttf", 36)
        except IOError:
            self.font = ImageFont.load_default()

    def generate(self, change_pct: float, state: str, has_error: bool = False) -> Image.Image:
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