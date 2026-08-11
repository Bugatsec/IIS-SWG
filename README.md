# IIS-SWG — IIS Shortname Wordlist Generator

![Python](https://img.shields.io/badge/python-3.x-blue?logo=python&logoColor=white)
![Selenium](https://img.shields.io/badge/selenium-4.15%2B-43B02A?logo=selenium&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL%20%7C%20Windows-lightgrey)
![Status](https://img.shields.io/badge/status-active-success)
![Stars](https://img.shields.io/github/stars/Bugatsec/IIS-SWG?style=social)
![Issues](https://img.shields.io/github/issues/Bugatsec/IIS-SWG)
![Last Commit](https://img.shields.io/github/last-commit/Bugatsec/IIS-SWG)

Automates fetching potential file and directory names based on the partial
names recovered by an IIS Tilde (`~`) shortname scanner. It drives a headless
Chrome/Chromium browser via Selenium to run GitHub code searches for a given
short-name fragment and collects matching path segments into a wordlist.

## Credits

This tool is based on the original **[gsnw](https://github.com/retkoussa/gsnw)**
by [@retkoussa](https://github.com/retkoussa). The original script targeted a
Windows + Chrome setup. This repository is an independent rewrite (not a fork)
adapted for a Linux / WSL (Kali) + Chromium workflow, with output formatting
and setup changes for that environment. All credit for the original concept
and implementation goes to the original author.

## Features

- Headless, Selenium-driven GitHub code search by path fragment
- Uses a dedicated, persistent Chromium profile so you only log in to GitHub once
- Paginates through search results automatically
- Deduplicates matched path segments across pages
- Colored console output for readability
- Silent mode to suppress the banner (`-silent`)
- Optional save-to-file output

## Requirements

- Python 3.x
- Google Chrome or Chromium installed
- `selenium` (see `requirements.txt`)

## Installation

```bash
git clone https://github.com/Bugatsec/IIS-SWG.git
cd IIS-SWG

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\Activate

pip install -r requirements.txt
```

## ⚠️ Chromium/Chrome Profile Setup (read this first)

At startup, the tool scans your machine for existing Chrome/Chromium
profiles (on Windows, Linux/WSL, and macOS) and shows you a picker:

```
[*] Found existing browser profile(s) on this machine:

  1) Chrome - Default - Ranveer (ranveer@example.com)
  2) Chrome - Profile 1 - Work
  3) Use a separate dedicated profile just for this tool (recommended, won't touch your main browser)

Select a profile to use [1-3] (default 3):
```

- **Pick your own profile** if you're already logged in to GitHub there.
  You'll need to close that browser window first — a profile that's
  currently open and locked can't be reused by the tool, and it'll
  automatically fall back to the dedicated profile if it detects that.
  Note: even when closed, headless automation sometimes fails to reuse a
  real profile's login session (Chrome/GitHub can treat an automated
  session differently from a normal one) — if you hit an auth wall here,
  switch to the dedicated profile below.
- **Pick the dedicated option (default)** to leave your main browser
  completely untouched. The tool creates and reuses its own separate
  profile named `iis-swg` at:
  ```
  ~/.config/iis-swg
  ```
  The first time this profile is created, the tool stops and prints a
  ready-to-paste command instead of trying (and failing) to search. It
  looks like this:
  ```
  [!] No existing 'iis-swg' profile found. Created a new one at:
      ~/.config/iis-swg

  [*] One-time setup needed before this tool can search GitHub:
    1) Open a new terminal window.
    2) Paste and run this command:

      "chromium" --user-data-dir="~/.config/iis-swg" --profile-directory=Default

    3) A Chromium/Chrome window will open. Log in to GitHub (or create a free account).
    4) Close that window.
    5) Come back here and re-run this tool - it will reuse that login automatically.
  ```
  Just follow those steps once; the tool exits after printing them so it
  doesn't waste a search attempt while you're not logged in yet.

Running with `-dedicated-profile` skips the picker entirely and always
uses the dedicated profile — useful for scripted/automated runs.

## Usage

```bash
python3 gsnw.py <search_query> [output_file] [-silent] [-dedicated-profile]
```

- `<search_query>` — the partial/short name fragment to search for in GitHub code paths
- `[output_file]` — optional, saves results to this file
- `-silent` — optional, suppresses the banner
- `-dedicated-profile` — optional, skips the profile picker and always uses the tool's own dedicated Chromium profile (no interactive prompt)

## Example

```bash
python3 gsnw.py sapmai output.txt -silent
```

Searches GitHub code for `sapmai` and saves matching path segments to `output.txt` without printing the banner.

## Notes

- Runs headless by default. To watch the browser live, remove/comment the `--headless=new` argument in `create_driver()`.
- Close any running Chromium instances before starting the tool — a second process can't attach to a profile that's already open.
- Be mindful of GitHub's rate limits; the script already waits between paginated requests.

## Disclaimer

Provided "as is" for authorized security testing and research only. Use it
only against systems and code you have permission to test. The author is not
responsible for misuse.

## Author

**@Bugatsec** — [github.com/Bugatsec](https://github.com/Bugatsec)
