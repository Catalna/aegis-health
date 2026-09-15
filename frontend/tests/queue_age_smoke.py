"""Behavior-level regression for queue-age formatting in the frontend contract."""

import argparse

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description="Test queue-age formatter edge cases")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(args.base_url, wait_until="domcontentloaded")
        result = page.evaluate(
            """async () => {
                const { formatQueueAge } = await import('/src/queueSummaryData.js')
                const now = Date.parse('2026-09-13T12:00:00Z')
                return {
                    minutes: formatQueueAge('2026-09-13T11:30:00Z', now),
                    hours: formatQueueAge('2026-09-13T09:00:00Z', now),
                    days: formatQueueAge('2026-09-10T12:00:00Z', now),
                    future: formatQueueAge('2026-09-13T13:00:00Z', now),
                    invalid: formatQueueAge('not-a-timestamp', now),
                    empty: formatQueueAge('', now),
                    missing: formatQueueAge(null, now),
                }
            }"""
        )
        assert result == {
            "minutes": "30 mnt",
            "hours": "3 jam",
            "days": "3 hari",
            "future": "0 mnt",
            "invalid": "—",
            "empty": "—",
            "missing": "—",
        }, result
        browser.close()


if __name__ == "__main__":
    main()
