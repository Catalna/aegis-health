"""Native Playwright smoke test for Monitoring analytics failure state."""

import argparse
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


EXPECTED_503_CONSOLE_ERROR = "Failed to load resource: the server responded with a status of 503 (Service Unavailable)"


def main():
    parser = argparse.ArgumentParser(description="Smoke test Monitoring analytics error state")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="id-ID")
        analytics_mode = {"failed": True}
        health_mode = {"failed": False}
        now = datetime.now(timezone.utc)

        def claim(status, received_at, **timestamps):
            return {
                "claim_id": f"QUEUE-{status}",
                "status": status,
                "received_at": received_at.isoformat(),
                "queue_sequence": 1,
                **{key: value.isoformat() for key, value in timestamps.items()},
            }

        queue_items = {
            "pending": [claim("pending", now - timedelta(minutes=30))],
            "scanning": [claim("scanning", now - timedelta(hours=5), analysis_started_at=now - timedelta(minutes=10))],
            "processed": [claim("processed", now - timedelta(hours=4), analysis_started_at=now - timedelta(hours=2), analyzed_at=now - timedelta(minutes=90))],
            "review_required": [claim("review_required", now - timedelta(hours=6), analysis_started_at=now - timedelta(minutes=20), analyzed_at=now - timedelta(minutes=15))],
            "verified": [claim("verified", now - timedelta(hours=8), analysis_started_at=now - timedelta(hours=2), analyzed_at=now - timedelta(minutes=89), verified_at=now - timedelta(minutes=30))],
        }
        console_errors = []
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error" and message.text != EXPECTED_503_CONSOLE_ERROR
            else None,
        )
        page.on("pageerror", lambda error: console_errors.append(str(error)))

        def route_api(route):
            parsed = urlparse(route.request.url)
            if parsed.path == "/api/analytics/dashboard":
                if analytics_mode["failed"]:
                    route.fulfill(status=503, json={"detail": "secret analytics hostname"})
                else:
                    route.fulfill(status=200, json={
                        "total_claims": 0,
                        "processed_claims": 0,
                        "high_risk_claims": 0,
                        "verified_claims": 0,
                        "potential_financial_exposure": 0,
                    })
                return
            if parsed.path == "/api/health":
                if health_mode["failed"]:
                    route.fulfill(status=503, json={"detail": "secret health credentials"})
                else:
                    route.fulfill(status=200, json={
                        "status": "ok",
                        "components": {"database": {"status": "ok"}},
                    })
                return
            if parsed.path == "/api/claims":
                query = parse_qs(parsed.query)
                items = queue_items.get(query.get("status", [""])[0], [])
                route.fulfill(status=200, json={"total": len(items), "items": items, "skip": 0, "limit": 1000})
                return
            route.continue_()

        page.route("**/api/**", route_api)
        page.goto(f"{args.base_url}/monitoring")
        page.wait_for_load_state("networkidle")

        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 900})
            expect(page.get_by_text("Data analitik gagal dimuat", exact=True)).to_be_visible()
            expect(page.get_by_text("Metrik belum tersedia; angka tidak ditampilkan sebagai nol.", exact=True)).to_be_visible()
            expect(page.get_by_role("heading", name="Ringkasan Pekerjaan dan Target Waktu")).to_be_visible()
            for label in ("Menunggu pemeriksaan", "Usia antrean tertua", "Rata-rata waktu pemeriksaan", "Rata-rata waktu verifikasi"):
                expect(page.get_by_text(label, exact=True)).to_be_visible()
            expect(page.get_by_text("Waktu pemeriksaan mencakup klaim yang sedang diperiksa atau sudah selesai.", exact=True)).to_be_visible()
            expect(page.get_by_text("Waktu verifikasi mencakup klaim yang menunggu atau sudah mendapat keputusan petugas.", exact=True)).to_be_visible()
            expect(page.get_by_text("Target:", exact=False)).to_have_count(3)
            expect(page.get_by_text("Perlu perhatian mulai:", exact=False)).to_have_count(3)
            expect(page.get_by_text("Mendekati batas:", exact=False)).to_have_count(3)
            expect(page.get_by_text("Melewati batas:", exact=False)).to_have_count(3)
            expect(page.get_by_text("Sisa", exact=False)).to_be_visible()
            for value in ("5 jam", "19,0 menit", "31,0 menit", "1,5 jam"):
                expect(page.get_by_text(value, exact=True)).to_be_visible()
            expect(page.get_by_text(re.compile(r"54,\d menit"))).to_be_visible()
            for target in ("Target: 4,0 jam", "Target: 30,0 menit", "Target: 24,0 jam"):
                expect(page.get_by_text(target, exact=False)).to_be_visible()
            queue_sla = page.locator('[data-sla="Target waktu antrean"]')
            expect(queue_sla).to_contain_text("Perlu perhatian mulai: 3,0 jam")
            expect(queue_sla).to_contain_text("Mendekati batas: 0")
            expect(queue_sla).to_contain_text("Melewati batas: 1")
            analysis_sla = page.locator('[data-sla="Target waktu pemeriksaan"]')
            expect(analysis_sla).to_contain_text("Perlu perhatian mulai: 22,5 menit")
            expect(analysis_sla).to_contain_text("Mendekati batas: 1")
            expect(analysis_sla).to_contain_text("Melewati batas: 1")
            retry = page.get_by_role("button", name="Coba lagi")
            expect(retry).to_be_visible()
            assert retry.evaluate("element => element.getBoundingClientRect().height") >= 44, width
            assert page.get_by_text("—", exact=True).count() >= 4
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
            assert "secret" not in page.locator("body").inner_text().lower()
            page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
            axe_result = page.evaluate("async () => await axe.run()")
            violations = [(violation["id"], violation["impact"]) for violation in axe_result["violations"]]
            assert not violations, violations

        analytics_mode["failed"] = False
        page.get_by_role("button", name="Coba lagi").click()
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Data analitik gagal dimuat", exact=True)).to_have_count(0)
        assert page.get_by_text("0", exact=True).count() >= 4

        health_mode["failed"] = True
        page.wait_for_timeout(5500)
        expect(page.get_by_text("Layanan pemeriksaan belum dapat dihubungi.", exact=True)).to_be_visible()
        expect(page.get_by_text("Penyimpanan data klaim", exact=True)).to_be_visible()
        expect(page.get_by_text("Penyimpanan data tersedia", exact=True)).to_be_visible()
        expect(page.get_by_text("Gangguan", exact=True)).to_be_visible()
        assert "secret" not in page.locator("body").inner_text().lower()
        health_retry = page.get_by_role("button", name="Coba lagi")
        expect(health_retry).to_be_visible()
        assert page.locator(".monitoring-health-state").get_attribute("role") == "alert"
        page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
        axe_result = page.evaluate("async () => await axe.run()")
        violations = [(violation["id"], violation["impact"]) for violation in axe_result["violations"]]
        assert not violations, violations

        health_mode["failed"] = False
        health_retry.click()
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("Layanan pemeriksaan belum dapat dihubungi.", exact=True)).to_have_count(0)
        expect(page.locator(".monitoring-live-status")).to_contain_text("Sehat")

        assert not console_errors, console_errors
        browser.close()


if __name__ == "__main__":
    main()
