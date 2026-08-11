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
import time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
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
    "~/.config/gsnw-chromium"
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


def select_chrome_profile(interactive=True):
    """
    Detect the user's own Chrome/Chromium profiles and let
    them choose to use one directly, or fall back to a
    separate dedicated profile just for this tool.

    Returns (user_data_dir, profile_directory, is_dedicated)
    """

    detected = []

    for browser_name, root in get_chrome_data_roots():

        for dir_name, label in list_profiles_in_root(root):

            detected.append((
                root,
                dir_name,
                f"{browser_name} - {label}"
            ))

    dedicated_label = (
        "Use a separate dedicated profile just for this "
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


def create_driver(interactive=True):

    chrome_options = Options()

    # --------------------------------------------------
    # Locate Chrome/Chromium for this OS
    # --------------------------------------------------

    browser_binary = find_browser_binary()

    if browser_binary:

        chrome_options.binary_location = browser_binary

    else:

        print(
            f"{Color.YELLOW}[!] Could not auto-detect a Chrome/Chromium "
            f"install. Letting Selenium try to locate it.{Color.RESET}"
        )

    # Headless
    chrome_options.add_argument("--headless=new")

    # Sandbox/GPU flags: required on Linux/WSL, harmless on Windows
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # Reduce output
    chrome_options.add_argument("--log-level=3")

    # --------------------------------------------------
    # Pick a profile: user's own, or a dedicated one
    # --------------------------------------------------

    user_data_dir, profile_directory, is_dedicated = select_chrome_profile(
        interactive=interactive
    )

    if is_dedicated:

        profile_already_existed = os.path.isdir(user_data_dir)

        if profile_already_existed:

            print(
                f"{Color.CYAN}[*] Using existing dedicated profile: "
                f"{user_data_dir}{Color.RESET}"
            )

        else:

            os.makedirs(user_data_dir, exist_ok=True)

            print(
                f"{Color.YELLOW}[!] No existing dedicated profile found. "
                f"Created a new one at:{Color.RESET}"
            )

            print(f"    {user_data_dir}")

            print(
                f"{Color.YELLOW}[!] This profile isn't logged in to "
                f"GitHub yet. Log in once by running:{Color.RESET}"
            )

            print(
                f"    chromium --user-data-dir=\"{user_data_dir}\""
            )

            print(
                f"{Color.YELLOW}[!] Log in to GitHub in that window, "
                f"then close it and re-run this tool.{Color.RESET}"
            )

    chrome_options.add_argument(
        f"--user-data-dir={user_data_dir}"
    )

    chrome_options.add_argument(
        f"--profile-directory={profile_directory}"
    )

    # --------------------------------------------------
    # Start browser
    # --------------------------------------------------

    driver = webdriver.Chrome(
        options=chrome_options
    )

    driver.set_page_load_timeout(30)

    return driver


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

    driver = create_driver(interactive=interactive)

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

                    print()
                    print(
                        f"{Color.RED}[!] GitHub requires "
                        f"authentication for code search.{Color.RESET}"
                    )

                    print(
                        "[!] Login using the profile:"
                    )

                    print(
                        "    ~/.config/gsnw-chromium"
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

    finally:

        driver.quit()

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
