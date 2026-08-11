# IIS-SWG — IIS Shortname Wordlist Generator

<p align="left">
  <img src="https://img.shields.io/badge/python-3.x-blue?logo=python&logoColor=white" alt="Python 3.x">
  <img src="https://img.shields.io/badge/built%20with-Selenium-43B02A?logo=selenium&logoColor=white" alt="Built with Selenium">
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20WSL%20-informational" alt="Platform">
  <img src="https://img.shields.io/github/stars/Bugatsec/IIS-Shortname-Wordlist-Generator?style=social" alt="Stars">
  <img src="https://img.shields.io/github/forks/Bugatsec/IIS-Shortname-Wordlist-Generator?style=social" alt="Forks">
  <img src="https://img.shields.io/github/issues/Bugatsec/IIS-Shortname-Wordlist-Generator" alt="Issues">
  <img src="https://img.shields.io/github/last-commit/Bugatsec/IIS-Shortname-Wordlist-Generator" alt="Last commit">
</p>

Automates the process of fetching potential file and directory names based on the partial 8.3 short names leaked by an IIS Tilde (`~`) shortname enumeration scan. It drives a headless Chromium instance via Selenium to search GitHub code for path segments matching those partial names, so you can turn short, truncated hints into a usable wordlist.

## Credits

This tool is based on the original **[gsnw](https://github.com/retkoussa/gsnw)** by [retkoussa](https://github.com/retkoussa) ([@retkoussa on X](https://twitter.com/retkoussa)). All core logic and the original idea belong to them.

This repository is **not a fork** — it's a standalone rewrite adapted specifically for running under **WSL Kali with Chromium**, since the original script targeted Windows + Google Chrome and did not work as-is in a WSL environment. Output formatting, banner, and Linux/WSL setup were changed; the search and extraction logic is unchanged from the original.

## Features

- Headless Chromium automation via Selenium (Selenium Manager auto-resolves the matching driver — no manual chromedriver install needed)
- Uses a dedicated, persistent Chromium profile so you stay logged in to GitHub between runs
- Extracts and deduplicates matching path segments from GitHub code search results across all result pages
- Optional silent mode to suppress the banner
- Optional output file to save results as a plain wordlist

## Requirements

- Python 3.x
- Chromium (not Google Chrome — this build targets the `chromium` binary at `/usr/bin/chromium`)
- WSL Kali (or another Linux environment with Chromium installed)
- A GitHub account (GitHub code search requires you to be signed in)

## Installation

```bash
git clone https://github.com/Bugatsec/IIS-Shortname-Wordlist-Generator.git
cd IIS-Shortname-Wordlist-Generator

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Make sure Chromium is installed on your WSL Kali system:

```bash
sudo apt update
sudo apt install chromium -y
```

## First-Time Setup — Logging in to GitHub (Important)

GitHub code search requires an authenticated session. The script uses its **own dedicated Chromium profile** (`~/.config/gsnw-chromium`) so your login persists between runs without touching your regular browser profile.

If you're running this on Linux/WSL and Chromium isn't already configured or logged in to GitHub the way it is on the original author's Windows profile, you need to log in once, manually, using the **exact same profile path** the script uses:

```bash
chromium --user-data-dir=~/.config/gsnw-chromium --profile-directory=Default
```

1. Run the command above — this opens a normal (non-headless) Chromium window using the same profile the script will later use headlessly.
2. Go to `github.com` and sign in to any GitHub account (or create a new one).
3. Close Chromium once you're logged in.
4. Run the script normally — it will now reuse that session in headless mode.

If you skip this step, the script will detect that GitHub is asking you to sign in and will exit early with a message telling you to log in via that same profile.

## Usage

```bash
python3 gsnw.py <search_query> [output_file] [-silent]
```

- `<search_query>` — the partial name to search for in GitHub code paths (e.g. a truncated 8.3 shortname).
- `[output_file]` — optional, path to save results as a plain-text wordlist.
- `-silent` — optional, suppresses the startup banner.

### Example

```bash
python3 gsnw.py sapmai output.txt -silent
```

Searches GitHub code for `sapmai` and saves matching path segments to `output.txt` without showing the banner.

## Notes

- Runs headless by default. To watch the browser while it works (useful for debugging), comment out the `--headless=new` argument in `create_driver()`.
- Close any other Chromium instances using the same profile before running — a locked profile directory will cause the driver to fail to start.
- Tested on WSL Kali. Should work on any Linux distro with Chromium installed, given the hardcoded `/usr/bin/chromium` binary path.
- Not tested on native Windows or macOS in this rewrite — see the original repo if you need a Windows-first version.

## Disclaimer

This script is provided "as is" without any warranties. Use it at your own risk, and only against targets and code you have permission to search or test against.

## Author

**@Bugatsec**
GitHub: [https://github.com/Bugatsec](https://github.com/Bugatsec)
