"""
IIS-SWG - IIS Shortname Wordlist Generator

Search GitHub code paths and extract matching path segments.

Author : @Bugatsec (Ranveer Kohli)
GitHub : https://github.com/Bugatsec/IIS-Shortname-Wordlist-Generator
"""

import argparse
import logging
import os
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

def create_driver():

    chrome_options = Options()

    # Kali WSL Chromium
    chrome_options.binary_location = "/usr/bin/chromium"

    # Headless
    chrome_options.add_argument("--headless=new")

    # WSL-friendly
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # Reduce output
    chrome_options.add_argument("--log-level=3")

    # --------------------------------------------------
    # Dedicated GSNW Chromium profile
    # --------------------------------------------------

    chromium_profile = os.path.expanduser(
        "~/.config/gsnw-chromium"
    )

    chrome_options.add_argument(
        f"--user-data-dir={chromium_profile}"
    )

    chrome_options.add_argument(
        "--profile-directory=Default"
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

def search_github(query):

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

    driver = create_driver()

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

    args = parser.parse_args()

    if not args.silent:
        print(BANNER)

    matched_words = search_github(
        args.search_query
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
