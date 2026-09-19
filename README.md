# TickerIcon

[![Tests](https://github.com/bolohamwich/TickerIcon/actions/workflows/tests.yml/badge.svg)](https://github.com/bolohamwich/TickerIcon/actions/workflows/tests.yml)
[![Latest Release](https://img.shields.io/github/v/release/bolohamwich/TickerIcon)](https://github.com/bolohamwich/TickerIcon/releases/latest)
[![License: MIT](https://img.shields.io/github/license/bolohamwich/TickerIcon)](LICENSE)

A lightweight, open-source Windows application that embeds a live, automatically updating stock ticker directly into the system tray. 
Relies on Yahoo Finance for 1-minute updates during regular, pre-market, and after-hours trading sessions.

## Features
* **At-a-glance:** The icon displays the daily percentage change, colored green or red (drops decimals for double-digit moves to ensure taskbar readability), on a static background. A thin strip along the bottom of the icon is color-coded for market state (premarket, open, after hours, closed) and turns to the error color when data can't be fetched — in which case the icon keeps showing the last known values. The strip width is configurable and can be set to 0 to disable it.
* **Detailed Tooltips:** Hover over the icon to instantly see current price, exact percentage change, day high, and day low.
* **Sleep:** Automatically suspends network requests overnight and on weekends.
* **Updates:** Use the tray menu's **Check for Updates** command to see whether a newer release is available and open its download page.

## Prerequisites
* Windows 10 or 11

## Installation

1. Download `TickerIcon-Setup.exe` from the [latest release](https://github.com/bolohamwich/TickerIcon/releases/latest).
2. Run the installer and follow the setup prompts.
3. Launch TickerIcon from the Start Menu.

If you prefer a portable copy, each release also includes `TickerIcon.zip`.

## Usage

Launch TickerIcon from the Start Menu or by opening the installed application directly. It runs silently in the background without opening a command prompt window. 

*Note: Windows hides new tray icons in the overflow menu by default. Click the up-arrow `^` on your taskbar and drag the new stock icon down to the visible portion of your taskbar so it is always visible.*

### Tray Icon Menu

Click the tray icon to jump to the next symbol immediately (in both display modes). Right-click it to open the context menu:

* **Next Symbol** jumps to the next enabled symbol, same as clicking the icon.
* **Symbols** lists every configured symbol with a checkmark; toggle one to show or hide it. This only filters the display — data is still fetched for all configured symbols — and the last enabled symbol cannot be hidden.
* **Settings** opens the configuration window.
* **Pause** temporarily stops price updates and switches the tray icon to a paused state until you unpause it.
* **Check for Updates** looks for a newer release on GitHub and, if one is found, offers to open its download page in your browser.
* **Quit** closes the application.

### Settings

The **Settings** window lets you update:

* the list of tracked ticker symbols (up to ten symbols)
* positive, negative, error-strip, and market-state strip colors (the "closed" color is also the static icon background)
* scroll speed
* how long each price stays visible
* the icon font size
* the width of the market-state/error strip at the bottom of the icon (0 disables it)
* whether all tracked symbols scroll continuously in one line

After you save your changes, TickerIcon reloads the configuration automatically.

### Updates

Use **Check for Updates** from the tray icon menu to look for a newer release. When an update is available, TickerIcon shows a prompt announcing the new version and asking whether to open the download page; choosing **Yes** opens the release page in your default browser (in a new tab if the browser is already running). Download and run the new `TickerIcon-Setup.exe` from there — reinstalling with a newer installer upgrades the app in place and keeps your existing `config.cfg`.

## Running on Startup
Choose **Start TickerIcon when I sign in to Windows** during installation if you want it to launch automatically at sign-in. If you skipped that option, run the latest installer again and enable the startup option.

## Building a Windows Package

Python is only required when running the project from source or building release artifacts.

Build the application on Windows because PyInstaller produces a
platform-specific executable:

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m PyInstaller --clean --noconfirm tickericon.spec
copy config.cfg dist\TickerIcon\config.cfg
```

The resulting `dist\TickerIcon` folder is the input to
`installer\TickerIcon.iss`. Compile that file with Inno Setup 6 to create a
per-user installer. The installer uses the icon in
`assets\tickericon.ico`, creates a Start Menu shortcut, and optionally adds
the application to Windows startup.

Publishing a GitHub Release runs the same Windows build automatically through
`.github\workflows\release.yml`. The release receives
`TickerIcon-Setup.exe` as the one-file installer and `TickerIcon.zip` as the
portable distribution. The updater reads the published release tag as the
application version and uses the installer asset over HTTPS.

## License
Distributed under the MIT License. See `LICENSE` for more information.