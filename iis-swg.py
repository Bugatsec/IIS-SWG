"""
IIS-SWG - IIS Shortname Wordlist Generator

Search GitHub code paths and extract matching path segments.

Author : @Bugatsec
GitHub : https://github.com/Bugatsec/IIS-Shortname-Wordlist-Generator
"""

import argparse
import json
import logging
import os
import platform
import shutil
import subprocess
import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


# --------------------------------------------------
# Colors
# --------------------------------------------------

class Color:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# Enable ANSI colors on Windows terminals
if os.name == "nt":
    os.system("")


# --------------------------------------------------
# Banner
# --------------------------------------------------

BANNER = f"""{Color.CYAN}
=================================================={Color.RESET}
{Color.BOLD}   IIS-SWG - IIS Shortname Wordlist Generator{Color.RESET}
{Color.CYAN}=================================================={Color.RESET}
        by @Bugatsec
        https://github.com/Bugatsec/IIS-Shortname-Wordlist-Generator
{Color.CYAN}=================================================={Color.RESET}
"""


# --------------------------------------------------
# Logging
# --------------------------------------------------

logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# --------------------------------------------------
# Browser
# --------------------------------------------------

def find_browser_binary():
    """
    Locate an installed Chrome/Chromium binary across
    Windows, Linux/WSL, and macOS.

    Returns the full path if found, or None to let
    Selenium's own auto-detection (Selenium Manager)
    try instead.
    """

    system = platform.system()
    candidates = []

    if system == "Windows":

        candidates = [
            os.path.expandvars(
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
            ),
            os.path.expandvars(
                r"%ProgramFiles%\Chromium\Application\chrome.exe"
            ),
        ]

    elif system == "Darwin":

        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]

    else:

        # Linux / WSL
        for name in (
            "chromium",
            "chromium-browser",
            "google-chrome",
            "google-chrome-stable",
        ):

            found = shutil.which(name)

            if found:
                candidates.append(found)

        candidates += [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
        ]

    for path in candidates:

        if path and os.path.isfile(path):
            return path

    return None


# --------------------------------------------------
# Profile detection
# --------------------------------------------------

DEDICATED_PROFILE_DIR = os.path.expanduser(
    "~/.config/iis-swg"
)


def get_chrome_data_roots():
    """
    Return (browser_name, user_data_dir) candidates for
    the user's own, real Chrome/Chromium installs, per OS.
    """

    system = platform.system()
    roots = []

    if system == "Windows":

        roots.append((
            "Chrome",
            os.path.expandvars(
                r"%LocalAppData%\Google\Chrome\User Data"
            )
        ))

        roots.append((
            "Chromium",
            os.path.expandvars(
                r"%LocalAppData%\Chromium\User Data"
            )
        ))

    elif system == "Darwin":

        home = os.path.expanduser("~")

        roots.append((
            "Chrome",
            os.path.join(
                home,
                "Library/Application Support/Google/Chrome"
            )
        ))

        roots.append((
            "Chromium",
            os.path.join(
                home,
                "Library/Application Support/Chromium"
            )
        ))

    else:

        home = os.path.expanduser("~")

        roots.append((
            "Chrome",
            os.path.join(home, ".config/google-chrome")
        ))

        roots.append((
            "Chromium",
            os.path.join(home, ".config/chromium")
        ))

    return roots


def list_profiles_in_root(root_path):
    """
    Return [(profile_dir_name, display_label), ...] for a
    given Chrome/Chromium user-data-dir, reading each
    profile's Preferences file for a friendlier label.
    """

    profiles = []

    if not os.path.isdir(root_path):
        return profiles

    for entry in sorted(os.listdir(root_path)):

        if entry != "Default" and not entry.startswith("Profile "):
            continue

        profile_path = os.path.join(root_path, entry)

        if not os.path.isdir(profile_path):
            continue

        label = entry
        prefs_path = os.path.join(profile_path, "Preferences")

        if os.path.isfile(prefs_path):

            try:

                with open(prefs_path, "r", encoding="utf-8") as f:
                    prefs = json.load(f)

                name = prefs.get("profile", {}).get("name")

                accounts = prefs.get("account_info", [])
                email = accounts[0].get("email") if accounts else None

                if name and email:
                    label = f"{entry} - {name} ({email})"
                elif name:
                    label = f"{entry} - {name}"
                elif email:
                    label = f"{entry} - {email}"

            except Exception:
                pass

        profiles.append((entry, label))

    return profiles


def is_profile_locked(user_data_dir):
    """
    Best-effort check for whether a profile is currently
    open in a running browser (Chrome/Chromium create a
    SingletonLock symlink while running, on Linux/macOS).
    Not fully reliable on Windows, so treated as advisory.
    """

    lock_path = os.path.join(user_data_dir, "SingletonLock")
    return os.path.islink(lock_path) or os.path.exists(lock_path)


LOCK_FILE_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def profile_lock_files(user_data_dir):
    """
    Return any Chrome singleton lock files present in this
    profile directory - a sign a Chrome process still has,
    or still thinks it has, this profile open.
    """

    found = []

    for name in LOCK_FILE_NAMES:

        path = os.path.join(user_data_dir, name)

        if os.path.exists(path) or os.path.islink(path):
            found.append(path)

    return found


def kill_processes_for_profile(user_data_dir):
    """
    Best-effort, dependency-free: terminate any Chrome/
    Chromium processes whose command line references this
    profile directory - e.g. a chrome.exe left running
    after a Ctrl+C.
    """

    system = platform.system()
    killed_any = False

    try:

        if system == "Windows":

            ps_filter = user_data_dir.replace("'", "''")

            ps_cmd = (
                "Get-CimInstance Win32_Process -Filter "
                "\"Name='chrome.exe'\" | "
                f"Where-Object {{ $_.CommandLine -like "
                f"'*{ps_filter}*' }} | "
                "Select-Object -ExpandProperty ProcessId"
            )

            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=15
            )

            for pid in result.stdout.splitlines():

                pid = pid.strip()

                if not pid.isdigit():
                    continue

                subprocess.run(
                    ["taskkill", "/F", "/PID", pid],
                    capture_output=True
                )

                killed_any = True

        else:

            result = subprocess.run(
                ["pgrep", "-f", user_data_dir],
                capture_output=True,
                text=True,
                timeout=15
            )

            for pid in result.stdout.splitlines():

                pid = pid.strip()

                if not pid.isdigit():
                    continue

                try:
                    os.kill(int(pid), 9)
                    killed_any = True
                except Exception:
                    pass

    except Exception:
        pass

    return killed_any


def clear_stale_lock(user_data_dir, interactive=True):
    """
    If the dedicated profile looks like it's still 'open'
    (e.g. Ctrl+C during a previous scan left chrome.exe
    running), offer to - or in non-interactive mode, just
    go ahead and - close it so this run doesn't fail with
    a 'profile already in use' error.
    """

    if not profile_lock_files(user_data_dir):
        return

    print()
    print(
        f"{Color.YELLOW}[!] The 'iis-swg' profile looks like it's "
        f"still open - probably left over from a previous run that "
        f"was interrupted (e.g. Ctrl+C).{Color.RESET}"
    )

    do_close = True

    if interactive:

        try:

            choice = input(
                "Close it now so this run can start cleanly? [Y/n]: "
            ).strip().lower()

        except (EOFError, KeyboardInterrupt):

            choice = "y"

        do_close = choice in ("", "y", "yes")

    if not do_close:
        return

    kill_processes_for_profile(user_data_dir)

    # Give the OS a moment to release file handles.
    for _ in range(5):

        if not profile_lock_files(user_data_dir):
            break

        time.sleep(1)

    for path in profile_lock_files(user_data_dir):

        try:
            os.remove(path)
        except Exception:
            pass

    if profile_lock_files(user_data_dir):

        print(
            f"{Color.RED}[!] Couldn't fully clear the lock. You may "
            f"need to close it manually or reboot.{Color.RESET}"
        )

    else:

        print(
            f"{Color.GREEN}[*] Profile freed up.{Color.RESET}"
        )


def cleanup_profile(user_data_dir):
    """
    Called after a scan ends (normally, on error, or on
    Ctrl+C) to make sure nothing is left holding the
    dedicated profile open for next time.
    """

    kill_processes_for_profile(user_data_dir)

    for path in profile_lock_files(user_data_dir):

        try:
            os.remove(path)
        except Exception:
            pass


def select_chrome_profile(interactive=True):
    """
    Detect the user's own Chrome/Chromium profiles and let
    them choose to use one directly, or fall back to a
    separate dedicated profile just for this tool.

    Returns (user_data_dir, profile_directory, is_dedicated)
    """

    # --------------------------------------------------
    # Already set up before? Just use it - don't ask
    # every single run.
    # --------------------------------------------------

    if os.path.isdir(DEDICATED_PROFILE_DIR):

        print(
            f"{Color.CYAN}[*] Using existing dedicated 'iis-swg' "
            f"profile.{Color.RESET}"
        )

        return DEDICATED_PROFILE_DIR, "Default", True

    detected = []

    for browser_name, root in get_chrome_data_roots():

        for dir_name, label in list_profiles_in_root(root):

            detected.append((
                root,
                dir_name,
                f"{browser_name} - {label}"
            ))

    dedicated_label = (
        "Use a separate dedicated 'iis-swg' profile just for this "
        "tool (recommended, won't touch your main browser)"
    )

    # Nothing detected, or non-interactive run: go straight
    # to the dedicated profile, no prompt.
    if not detected or not interactive:

        if detected:

            print(
                f"{Color.CYAN}[*] Existing browser profiles found, but "
                f"running non-interactively - using the dedicated "
                f"profile.{Color.RESET}"
            )

        return DEDICATED_PROFILE_DIR, "Default", True

    print(
        f"{Color.CYAN}[*] Found existing browser profile(s) on this "
        f"machine:{Color.RESET}"
    )

    print()

    for i, (root, dir_name, label) in enumerate(detected, 1):
        print(f"  {i}) {label}")

    dedicated_choice_num = len(detected) + 1

    print(f"  {dedicated_choice_num}) {dedicated_label}")
    print()

    try:

        choice = input(
            f"Select a profile to use "
            f"[1-{dedicated_choice_num}] "
            f"(default {dedicated_choice_num}): "
        ).strip()

    except (EOFError, KeyboardInterrupt):

        choice = ""

    try:

        idx = int(choice) if choice else dedicated_choice_num

    except ValueError:

        idx = dedicated_choice_num

    if idx == dedicated_choice_num or idx < 1 or idx > dedicated_choice_num:
        return DEDICATED_PROFILE_DIR, "Default", True

    chosen_root, chosen_dir, chosen_label = detected[idx - 1]

    if is_profile_locked(chosen_root):

        print()
        print(
            f"{Color.RED}[!] '{chosen_label}' looks like it's currently "
            f"open in a browser window.{Color.RESET}"
        )

        print(
            f"{Color.RED}[!] Close that browser first if you want to "
            f"reuse it, or this run will fall back to the dedicated "
            f"profile now.{Color.RESET}"
        )

        return DEDICATED_PROFILE_DIR, "Default", True

    print(
        f"{Color.GREEN}[*] Using your profile: {chosen_label}{Color.RESET}"
    )

    return chosen_root, chosen_dir, False


def launch_chrome(chrome_options, is_dedicated=False):
    """
    Start a Chrome/Chromium session. If the profile is
    already locked by another running Chrome process (a
    very common Windows gotcha - Chrome keeps chrome.exe
    alive in the background even after you close every
    window, unless 'Continue running background apps' is
    turned off), this turns Selenium's raw crash traceback
    into a clear, actionable message instead.
    """

    try:

        driver = webdriver.Chrome(options=chrome_options)

    except WebDriverException as e:

        message = str(e)

        profile_in_use = (
            "DevToolsActivePort" in message
            or "user data directory is already in use" in message
            or "cannot connect to chrome" in message.lower()
        )

        if not profile_in_use:
            raise

        print()
        print(
            f"{Color.RED}[!] Chrome couldn't start with this profile - "
            f"it's almost certainly already open elsewhere.{Color.RESET}"
        )

        if is_dedicated:

            print(
                f"{Color.YELLOW}[!] Close any window using the "
                f"'iis-swg' profile and try again.{Color.RESET}"
            )

        else:

            print(
                f"{Color.YELLOW}[!] Close every Chrome window using "
                f"that profile and try again, or re-run and pick the "
                f"dedicated 'iis-swg' profile instead so it never "
                f"touches your main browser.{Color.RESET}"
            )

        print(
            f"{Color.YELLOW}[!] On Windows, Chrome often keeps running "
            f"in the background even after you close every window "
            f"(Settings > 'Continue running background apps when "
            f"Google Chrome is closed'). Check Task Manager for a "
            f"lingering chrome.exe and end it if the window close "
            f"doesn't fix it.{Color.RESET}"
        )

        raise SystemExit(1)

    driver.set_page_load_timeout(30)

    return driver


def build_chrome_options(
    user_data_dir,
    profile_directory,
    browser_binary,
    headless=True
):
    """
    Build a Chrome/Chromium Options object bound to a
    specific profile, optionally headless.
    """

    chrome_options = Options()

    if browser_binary:
        chrome_options.binary_location = browser_binary

    if headless:
        chrome_options.add_argument("--headless=new")

    # Sandbox/GPU flags: required on Linux/WSL, harmless on Windows
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # Reduce output
    chrome_options.add_argument("--log-level=3")

    chrome_options.add_argument(
        f"--user-data-dir={user_data_dir}"
    )

    chrome_options.add_argument(
        f"--profile-directory={profile_directory}"
    )

    return chrome_options


def interactive_github_login(
    user_data_dir,
    profile_directory,
    browser_binary,
    timeout=900
):
    """
    Open a *visible* browser window bound to the given
    profile so the user can log in to GitHub, then close
    the window automatically once a logged-in session is
    detected. Returns True if login was confirmed, False
    otherwise (timeout, or the user closed the window
    themselves before finishing).
    """

    print()
    print(
        f"{Color.CYAN}[*] Opening a browser window so you can log in "
        f"to GitHub...{Color.RESET}"
    )
    print(
        f"{Color.YELLOW}[!] Log in to your GitHub account (or create a "
        f"free one) in the window that opens.{Color.RESET}"
    )
    print(
        f"{Color.YELLOW}[!] The window will close on its own once "
        f"you're logged in - you don't need to close it "
        f"yourself.{Color.RESET}"
    )
    print()

    chrome_options = build_chrome_options(
        user_data_dir,
        profile_directory,
        browser_binary,
        headless=False
    )

    driver = launch_chrome(chrome_options, is_dedicated=True)

    try:

        driver.get("https://github.com/login")

        start_time = time.time()

        while time.time() - start_time < timeout:

            time.sleep(2)

            try:

                cookie = driver.get_cookie("logged_in")

                if cookie and cookie.get("value") == "yes":
                    logged_in = True
                    break

            except WebDriverException:

                # The window/browser was closed before we
                # could confirm login.
                print(
                    f"{Color.RED}[!] Browser window was closed before "
                    f"login was detected.{Color.RESET}"
                )

                return False

        if logged_in:

            print(
                f"{Color.GREEN}[*] Logged in! Closing the browser "
                f"window...{Color.RESET}"
            )

        else:

            print(
                f"{Color.RED}[!] Timed out waiting for login.{Color.RESET}"
            )

    finally:

        try:
            driver.quit()
        except Exception:
            pass

    return logged_in


def create_driver(interactive=True):

    # --------------------------------------------------
    # Locate Chrome/Chromium for this OS
    # --------------------------------------------------

    browser_binary = find_browser_binary()

    if not browser_binary:

        print(
            f"{Color.YELLOW}[!] Could not auto-detect a Chrome/Chromium "
            f"install. Letting Selenium try to locate it.{Color.RESET}"
        )

    # --------------------------------------------------
    # Pick a profile: user's own, or the dedicated one
    # --------------------------------------------------

    user_data_dir, profile_directory, is_dedicated = select_chrome_profile(
        interactive=interactive
    )

    first_run = is_dedicated and not os.path.isdir(user_data_dir)

    if is_dedicated and not first_run:
        clear_stale_lock(user_data_dir, interactive=interactive)

    if first_run:

        # --------------------------------------------------
        # First-time dedicated profile: create it and log
        # in right now ourselves, instead of asking the user
        # to go run a command in a separate terminal.
        # --------------------------------------------------

        os.makedirs(user_data_dir, exist_ok=True)

        print(
            f"{Color.YELLOW}[!] No existing 'iis-swg' profile found. "
            f"Created a new one at:{Color.RESET}"
        )
        print(f"    {user_data_dir}")

        logged_in = interactive_github_login(
            user_data_dir,
            profile_directory,
            browser_binary
        )

        if not logged_in:

            print(
                f"{Color.RED}[!] Could not confirm GitHub login. Re-run "
                f"the tool to try again.{Color.RESET}"
            )

            raise SystemExit(1)

    elif is_dedicated:

        print(
            f"{Color.CYAN}[*] Using dedicated 'iis-swg' profile: "
            f"{user_data_dir}{Color.RESET}"
        )

    # --------------------------------------------------
    # Start browser (headless)
    # --------------------------------------------------

    chrome_options = build_chrome_options(
        user_data_dir,
        profile_directory,
        browser_binary,
        headless=True
    )

    driver = launch_chrome(chrome_options, is_dedicated=is_dedicated)

    return driver, user_data_dir, profile_directory, is_dedicated, browser_binary


# --------------------------------------------------
# Extract matching segments
# --------------------------------------------------

def extract_matches(driver, query, matched_words):

    query_lower = query.lower()
    new_matches = 0

    elements = driver.find_elements(
        By.CSS_SELECTOR,
        'a[href*="/blob/"]'
    )

    print(
        f"{Color.CYAN}[+] Found {len(elements)} candidate links{Color.RESET}"
    )

    # Keep track of complete files we've already processed
    processed_files = set()

    for element in elements:

        try:
            href = element.get_attribute("href")

            if not href:
                continue

            if "/blob/" not in href:
                continue

            # Remove #L1, #L2, etc.
            href = href.split("#", 1)[0]

            if href in processed_files:
                continue

            processed_files.add(href)

            # --------------------------------------------------
            # Extract path after /blob/<branch>/
            # --------------------------------------------------

            blob_parts = href.split(
                "/blob/",
                1
            )

            if len(blob_parts) != 2:
                continue

            path_after_blob = blob_parts[1]

            # Remove branch name
            path_parts = path_after_blob.split(
                "/",
                1
            )

            if len(path_parts) != 2:
                continue

            file_path = path_parts[1]

            # --------------------------------------------------
            # Extract matching path components
            # --------------------------------------------------

            for segment in file_path.split("/"):

                segment = segment.strip()

                if not segment:
                    continue

                if query_lower not in segment.lower():
                    continue

                if segment in matched_words:
                    continue

                print(
                    f"    {Color.GREEN}[+] match -> {segment}{Color.RESET}"
                )

                matched_words.add(segment)
                new_matches += 1

        except StaleElementReferenceException:
            continue

        except Exception:
            continue

    return new_matches

# --------------------------------------------------
# Search GitHub
# --------------------------------------------------

def search_github(query, interactive=True):

    matched_words = set()
    page_number = 1

    encoded_query = quote_plus(
        f"path:/{query}"
    )

    base_url = (
        "https://github.com/search"
        f"?q={encoded_query}"
        "&type=code"
        "&p="
    )

    driver, user_data_dir, profile_directory, is_dedicated, browser_binary = (
        create_driver(interactive=interactive)
    )

    relogin_attempted = False

    try:

        while True:

            url = (
                f"{base_url}"
                f"{page_number}"
            )

            print()
            print(
                f"{Color.YELLOW}[*] Searching page "
                f"{page_number}: {url}{Color.RESET}"
            )

            try:

                driver.get(url)

                # --------------------------------------------------
                # Wait for body
                # --------------------------------------------------

                WebDriverWait(
                    driver,
                    15
                ).until(
                    lambda d: d.find_element(
                        By.TAG_NAME,
                        "body"
                    )
                )

                # --------------------------------------------------
                # Authentication check
                # --------------------------------------------------

                page_text = driver.find_element(
                    By.TAG_NAME,
                    "body"
                ).text

                if (
                    "Sign in to search code on GitHub"
                    in page_text
                ):

                    if is_dedicated and not relogin_attempted:

                        relogin_attempted = True

                        print()
                        print(
                            f"{Color.YELLOW}[!] Not logged in to GitHub "
                            f"yet.{Color.RESET}"
                        )

                        driver.quit()

                        logged_in = interactive_github_login(
                            user_data_dir,
                            profile_directory,
                            browser_binary
                        )

                        if not logged_in:

                            print(
                                f"{Color.RED}[!] Could not confirm "
                                f"GitHub login.{Color.RESET}"
                            )

                            break

                        chrome_options = build_chrome_options(
                            user_data_dir,
                            profile_directory,
                            browser_binary,
                            headless=True
                        )

                        driver = launch_chrome(chrome_options, is_dedicated=True)

                        # Retry the same page now that we're logged in.
                        continue

                    print()
                    print(
                        f"{Color.RED}[!] GitHub requires "
                        f"authentication for code search.{Color.RESET}"
                    )

                    print(
                        f"{Color.YELLOW}[!] If you picked your own "
                        f"browser profile, headless automation can fail "
                        f"to reuse its login session even when you're "
                        f"signed in normally.{Color.RESET}"
                    )

                    print(
                        f"{Color.YELLOW}[!] Re-run and choose the "
                        f"dedicated 'iis-swg' profile instead (or pass "
                        f"-dedicated-profile) and log in there once.{Color.RESET}"
                    )

                    break

                # --------------------------------------------------
                # Check for zero results
                # --------------------------------------------------

                lower_text = page_text.lower()

                if (
                    "your search did not match any"
                    in lower_text
                ):

                    print(
                        "[*] No results."
                    )

                    break

                # --------------------------------------------------
                # Extract results
                # --------------------------------------------------

                new_matches = extract_matches(
                    driver,
                    query,
                    matched_words
                )

                print(
                    f"{Color.YELLOW}[*] New matches on page "
                    f"{page_number}: "
                    f"{new_matches}{Color.RESET}"
                )

                # --------------------------------------------------
                # Find pagination
                # --------------------------------------------------

                next_buttons = driver.find_elements(
                    By.CSS_SELECTOR,
                    'a[rel="next"]'
                )

                # GitHub sometimes doesn't expose
                # rel="next", so use an href check too.
                if not next_buttons:

                    next_buttons = driver.find_elements(
                        By.CSS_SELECTOR,
                        'a[href*="&p="]'
                    )

                    valid_next = []

                    for button in next_buttons:

                        try:

                            href = (
                                button.get_attribute(
                                    "href"
                                )
                            )

                            if not href:
                                continue

                            if (
                                f"&p={page_number + 1}"
                                in href
                            ):
                                valid_next.append(
                                    button
                                )

                        except Exception:
                            continue

                    next_buttons = valid_next

                # --------------------------------------------------
                # No next page
                # --------------------------------------------------

                if not next_buttons:

                    print(
                        "[*] No next page found."
                    )

                    break

                page_number += 1

                # Don't hammer GitHub.
                time.sleep(2)

            except TimeoutException:

                print(
                    f"{Color.RED}[!] Page load timed out.{Color.RESET}"
                )

                save_debug_page(
                    driver,
                    page_number
                )

                break

            except Exception as e:

                print(
                    f"{Color.RED}[!] Error type: "
                    f"{type(e).__name__}{Color.RESET}"
                )

                print(
                    f"{Color.RED}[!] Error: {e}{Color.RESET}"
                )

                save_debug_page(
                    driver,
                    page_number
                )

                break

    except KeyboardInterrupt:

        print()
        print(
            f"{Color.YELLOW}[!] Stopped by user (Ctrl+C).{Color.RESET}"
        )

    finally:

        try:
            driver.quit()
        except Exception:
            pass

        if is_dedicated:

            # Belt and suspenders: make sure nothing is left
            # holding this profile open for next time, even
            # if we got here via Ctrl+C or a crash.
            cleanup_profile(user_data_dir)

    return sorted(
        matched_words,
        key=str.lower
    )


# --------------------------------------------------
# Debug helper
# --------------------------------------------------

def save_debug_page(driver, page_number):

    try:

        html_path = (
            f"/tmp/gsnw-page-{page_number}.html"
        )

        screenshot_path = (
            f"/tmp/gsnw-page-{page_number}.png"
        )

        with open(
            html_path,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                driver.page_source
            )

        driver.save_screenshot(
            screenshot_path
        )

        print(
            f"[!] HTML saved to: "
            f"{html_path}"
        )

        print(
            f"[!] Screenshot saved to: "
            f"{screenshot_path}"
        )

        print(
            "[!] Current URL:",
            driver.current_url
        )

        print(
            "[!] Page title:",
            driver.title
        )

    except Exception as e:

        print(
            f"[!] Could not save debug data: "
            f"{e}"
        )


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Search GitHub code paths. "
            "(IIS-SWG by @Bugatsec - "
            "https://github.com/Bugatsec/IIS-Shortname-Wordlist-Generator)"
        )
    )

    parser.add_argument(
        "search_query",
        help=(
            "Search term to look for in "
            "GitHub code paths"
        )
    )

    parser.add_argument(
        "output_file",
        nargs="?",
        default=None,
        help=(
            "Optional file to save results"
        )
    )

    parser.add_argument(
        "-silent",
        action="store_true",
        help="Suppress banner"
    )

    parser.add_argument(
        "-dedicated-profile",
        action="store_true",
        help=(
            "Skip the profile picker and always use the tool's own "
            "dedicated Chromium profile (no prompt, good for scripting)"
        )
    )

    args = parser.parse_args()

    if not args.silent:
        print(BANNER)

    matched_words = search_github(
        args.search_query,
        interactive=not args.dedicated_profile
    )

    # --------------------------------------------------
    # Output
    # --------------------------------------------------

    print()
    print(f"{Color.CYAN}{'=' * 50}{Color.RESET}")
    print(f" Query   : {args.search_query}")
    print(f" Matches : {Color.GREEN}{len(matched_words)}{Color.RESET}")
    print(f"{Color.CYAN}{'=' * 50}{Color.RESET}")

    if matched_words:

        for word in matched_words:
            print(f" {Color.GREEN}{word}{Color.RESET}")

    else:

        print(f" {Color.YELLOW}No matching paths found.{Color.RESET}")

    print(f"{Color.CYAN}{'=' * 50}{Color.RESET}")

    # --------------------------------------------------
    # Save output
    # --------------------------------------------------

    if args.output_file:

        with open(
            args.output_file,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                f"# IIS-SWG results for query: {args.search_query}\n"
            )
            file.write(
                "# Generated by @Bugatsec - "
                "https://github.com/Bugatsec/"
                "IIS-Shortname-Wordlist-Generator\n"
            )
            file.write(
                f"# Total matches: {len(matched_words)}\n\n"
            )

            for word in matched_words:

                file.write(
                    word + "\n"
                )

        print(
            f"[*] Results saved to "
            f"{args.output_file}"
        )


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    main()
