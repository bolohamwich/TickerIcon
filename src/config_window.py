try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover - only affects headless/non-Windows test environments
    tk = None
    messagebox = None
    ttk = None

from src.config_handler import ConfigHandler, DEFAULT_FONT_SIZE, DEFAULT_STRIP_WIDTH, MAX_STRIP_WIDTH, MAX_TICKERS


class ConfigWindow:
    """Simple settings dialog for editing the tray app's persisted config."""

    def __init__(self, config_path: str, config: dict, on_save=None):
        """Initialize the configuration dialog.

        Args:
            config_path (str): The path to the config.cfg file to edit.
            config (dict): The currently loaded configuration values.
            on_save (callable, optional): Callback triggered after a successful save.

        Raises:
            RuntimeError: If Tkinter is unavailable in the current environment.
        """
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter is not available in this environment.")

        self.config_path = config_path
        self.config = config
        self.on_save = on_save

        self.root = tk.Tk()
        self.root.title("TickerIcon Settings")
        self.root.geometry("540x550")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.entries = {}
        self._build_form()

    def _build_form(self):
        """Create all of the widgets for the configuration form.

        Returns:
            None: The form is built in-place on the window's root widget.
        """
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Tracked symbols (comma separated)", font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.entries["tickers"] = ttk.Entry(container, width=60)
        self.entries["tickers"].insert(0, ", ".join(self.config["tickers"]))
        self.entries["tickers"].pack(fill="x", pady=(0, 10))

        color_fields = [
            ("Positive", "color_positive"),
            ("Negative", "color_negative"),
            ("Error strip", "color_error_border"),
            ("Open", "bg_open"),
            ("Premarket", "bg_premarket"),
            ("After hours", "bg_after_hours"),
            ("Closed / background", "bg_closed"),
        ]

        for label_text, key in color_fields:
            row = ttk.Frame(container)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=f"{label_text} color", width=18).pack(side="left")
            entry = ttk.Entry(row, width=16)
            entry.insert(0, ConfigHandler._rgb_to_hex(self.config[key]))
            entry.pack(side="left")
            self.entries[key] = entry

        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=10)

        row = ttk.Frame(container)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Scroll speed (ms)", width=18).pack(side="left")
        speed = ttk.Entry(row, width=12)
        speed.insert(0, str(self.config["scroll_speed_ms"]))
        speed.pack(side="left")
        self.entries["scroll_speed_ms"] = speed

        row = ttk.Frame(container)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Display seconds", width=18).pack(side="left")
        display = ttk.Entry(row, width=12)
        display.insert(0, str(self.config["display_seconds"]))
        display.pack(side="left")
        self.entries["display_seconds"] = display

        row = ttk.Frame(container)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Icon font size (pt)", width=18).pack(side="left")
        font_size = ttk.Entry(row, width=12)
        font_size.insert(0, str(self.config.get("font_size", DEFAULT_FONT_SIZE)))
        font_size.pack(side="left")
        self.entries["font_size"] = font_size

        row = ttk.Frame(container)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Strip width (px)", width=18).pack(side="left")
        strip_width = ttk.Entry(row, width=12)
        strip_width.insert(0, str(self.config.get("strip_width", DEFAULT_STRIP_WIDTH)))
        strip_width.pack(side="left")
        self.entries["strip_width"] = strip_width

        self.continuous_scroll_var = tk.BooleanVar(value=self.config.get("continuous_scroll", True))
        ttk.Checkbutton(
            container,
            text="Scroll all symbols continuously in one line",
            variable=self.continuous_scroll_var,
        ).pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(16, 0))
        ttk.Button(actions, text="Save", command=self._save).pack(side="right")
        ttk.Button(actions, text="Cancel", command=self.root.destroy).pack(side="right", padx=(0, 8))

    def _save(self):
        """Validate the form, persist the config, and invoke the save callback.

        Returns:
            None: The user is notified through the dialog if validation fails.
        """
        try:
            config = self._collect_config()
            ConfigHandler(self.config_path).save(config)
            if self.on_save is not None:
                self.on_save(config)
            self.root.destroy()
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not write config file: {exc}")
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))

    def _collect_config(self) -> dict:
        """Read the form values and return a normalized configuration dict.

        Returns:
            dict: A configuration dictionary matching the repository's config schema.

        Raises:
            ValueError: If required values are missing or invalid.
        """
        tickers_raw = self.entries["tickers"].get().strip()
        if not tickers_raw:
            raise ValueError("At least one ticker is required.")

        tickers = [item.strip().upper() for item in tickers_raw.split(",") if item.strip()]
        if not tickers:
            raise ValueError("At least one ticker is required.")
        if len(tickers) > MAX_TICKERS:
            raise ValueError(f"Ticker list exceeds MAX_TICKERS ({MAX_TICKERS}).")

        def get_hex(key: str):
            value = self.entries[key].get().strip()
            if not value.startswith("#"):
                value = f"#{value}"
            try:
                return ConfigHandler._hex_to_rgb(value)
            except Exception as exc:  # pragma: no cover - GUI-side validation
                raise ValueError(f"{key.replace('_', ' ').title()} must be a hex color like #0FAF50") from exc

        try:
            scroll_speed_ms = int(self.entries["scroll_speed_ms"].get())
        except ValueError as exc:  # pragma: no cover - GUI-side validation
            raise ValueError("Scroll speed must be an integer.") from exc
        if scroll_speed_ms <= 0:
            raise ValueError("Scroll speed must be positive.")

        try:
            display_seconds = float(self.entries["display_seconds"].get())
        except ValueError as exc:  # pragma: no cover - GUI-side validation
            raise ValueError("Display seconds must be a number.") from exc
        if display_seconds <= 0:
            raise ValueError("Display seconds must be positive.")

        try:
            font_size = int(self.entries["font_size"].get())
        except ValueError as exc:  # pragma: no cover - GUI-side validation
            raise ValueError("Font size must be an integer.") from exc
        if font_size <= 0:
            raise ValueError("Font size must be positive.")

        try:
            strip_width = int(self.entries["strip_width"].get())
        except ValueError as exc:  # pragma: no cover - GUI-side validation
            raise ValueError("Strip width must be an integer.") from exc
        if not 0 <= strip_width <= MAX_STRIP_WIDTH:
            raise ValueError(f"Strip width must be between 0 and {MAX_STRIP_WIDTH}.")

        return {
            "tickers": tickers,
            "color_positive": get_hex("color_positive"),
            "color_negative": get_hex("color_negative"),
            "color_error_border": get_hex("color_error_border"),
            "bg_open": get_hex("bg_open"),
            "bg_premarket": get_hex("bg_premarket"),
            "bg_after_hours": get_hex("bg_after_hours"),
            "bg_closed": get_hex("bg_closed"),
            "scroll_speed_ms": scroll_speed_ms,
            "display_seconds": display_seconds,
            "continuous_scroll": bool(self.continuous_scroll_var.get()),
            "font_size": font_size,
            "strip_width": strip_width,
        }

    def show(self):
        """Start the Tkinter event loop for the settings window.

        Returns:
            None: This blocks until the window is closed.
        """
        self.root.mainloop()
