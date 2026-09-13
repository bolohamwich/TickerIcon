# TickerIcon

A lightweight, open-source Python application that embeds a live, automatically updating stock ticker directly into Windows system tray. 
Relies on Yahoo Finance for 1-minute updates during regular, pre-market, and after-hours trading sessions.

## Features
* **At-a-glance:** The icon displays the daily percentage change, colored green or red (drops decimals for double-digit moves to ensure taskbar readability). Icon background is color-coded for market state (premarket, open, after hours, closed). Red border around the background to indicate issues in connectivity.
* **Detailed Tooltips:** Hover over the icon to instantly see current price, exact percentage change, day high, and day low.
* **Sleep:** Automatically suspends network requests overnight and on weekends.

## Prerequisites
* Python 3.9 (or newer)
* Windows 10 or 11

## Installation

1. Clone or download this repository.
2. Open your terminal or command prompt in the folder directory.
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Start `main.pyw` to launch the application. Because it uses the `.pyw` extension, it will run silently in the background without opening a command prompt window. 

*Note: Windows hides new tray icons in the overflow menu by default. Click the up-arrow `^` on your taskbar and drag the new stock icon down to the visible portion of your taskbar so it is always visible.*

### Changing the Stock Symbols


## Running on Startup
1. Press `Win + R` to open the Run dialog.
2. Type `shell:startup` and press Enter.
3. Right-click inside the folder, select **New > Shortcut**.
4. Browse to your `main.pyw` file and complete the wizard.

## License
Distributed under the MIT License. See `LICENSE` for more information.