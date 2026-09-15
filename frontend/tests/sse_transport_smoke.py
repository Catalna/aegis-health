"""Focused browser regression for native EventSource transport failures."""

import argparse

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description="Smoke test empty-data SSE transport errors")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(args.base_url, wait_until="domcontentloaded")

        result = page.evaluate("""async () => {
            const events = []
            globalThis.EventSource = class {
                constructor() { this.listeners = {} }
                addEventListener(name, handler) { this.listeners[name] = handler }
                close() { events.push('close') }
            }
            const { createSSEStream } = await import('/src/api.js')
            const stream = createSSEStream('transport-error', {
                onError: (error) => events.push(`error:${error.message}`),
            })
            stream.listeners.error({ data: '' })
            return events
        }""")

        assert result == ["error:Koneksi stream terputus", "close"], result
        browser.close()


if __name__ == "__main__":
    main()
