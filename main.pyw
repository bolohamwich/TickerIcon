import sys
from pathlib import Path

from src.ticker_icon import TickerIcon


def _resolve_config_path() -> str:
    """Locates config.cfg next to the executable (frozen) or this script (dev)."""
    base_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    return str(base_dir / "config.cfg")


if __name__ == "__main__":
    app = TickerIcon(_resolve_config_path())
    app.start()
