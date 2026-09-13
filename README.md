# TickerIcon

[![Tests](https://github.com/bolohamwich/TickerIcon/actions/workflows/tests.yml/badge.svg)](https://github.com/bolohamwich/TickerIcon/actions/workflows/tests.yml)
[![Latest Release](https://img.shields.io/github/v/release/bolohamwich/TickerIcon)](https://github.com/bolohamwich/TickerIcon/releases/latest)
[![License: MIT](https://img.shields.io/github/license/bolohamwich/TickerIcon)](LICENSE)

A lightweight, open-source Windows application that embeds a live, automatically updating stock ticker directly into the system tray. 
Relies on Yahoo Finance for 1-minute updates during regular, pre-market, and after-hours trading sessions.

## Features
* **At-a-glance:** The icon displays the daily percentage change, colored green or red (drops decimals for double-digit moves to ensure taskbar readability). Icon background is color-coded for market state (premarket, open, after hours, closed). Red border around the background to indicate issues in connectivity.
* **Detailed Tooltips:** Hover over the icon to instantly see current price, exact percentage change, day high, and day low.
* **Sleep:** Automatically suspends network requests overnight and on weekends.
* **Updates:** Use the tray menu's **Check for Updates** command to download and launch the latest installer.

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

Right-click the tray icon to open the context menu:

* **Settings** opens the configuration window.
* **Pause** temporarily stops price updates and switches the tray icon to a paused state until you unpause it.
* **Check for Updates** downloads the latest installer from GitHub Releases and starts the upgrade process for you.
* **Quit** closes the application.

### Settings

The **Settings** window lets you update:

* the list of tracked ticker symbols (up to ten symbols)
* positive, negative, error-border, and market-state colors
* scroll speed
* how long each price stays visible
* whether all tracked symbols scroll continuously in one line

After you save your changes, TickerIcon reloads the configuration automatically.

### Updates

Use **Check for Updates** from the tray icon menu to look for a newer release. When an update is available, TickerIcon downloads the latest `TickerIcon-Setup.exe`, launches it, and exits so you can complete the installer. Reinstalling with a newer installer upgrades the app in place and keeps your existing `config.cfg`.

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