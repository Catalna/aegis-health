"""Native Playwright smoke test for the Task 2 claims lifecycle UI.

The API is mocked in the browser, so this test can run against a Vite frontend
without touching PostgreSQL or the shared claim dataset.
"""

import argparse
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Error as PlaywrightError, expect, sync_playwright


CLAIM_ID = "SMOKE-FAILED"
EXPECTED_503_CONSOLE_ERROR = "Failed to load resource: the server responded with a status of 503 (Service Unavailable)"


def wait_for_base_url(page, base_url, timeout=10):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = page.request.get(base_url, timeout=1000)
            if 200 <= response.status < 300:
                return
        except PlaywrightError as error:
            last_error = error
        time.sleep(0.1)
    raise RuntimeError(f"Frontend server did not become ready at {base_url}: {last_error}")


def goto_claims_and_wait(page, base_url, expected_total):
    def is_claims_response(response):
        parsed = urlparse(response.url)
        query = parse_qs(parsed.query)
        return (
            parsed.path == "/api/claims"
            and response.request.method == "GET"
            and response.status == 200
            and query.get("skip") == ["0"]
            and query.get("limit") == ["25"]
            and query.get("sort") == ["priority"]
        )

    for attempt in range(3):
        try:
            wait_for_base_url(page, base_url)
            with page.expect_response(is_claims_response, timeout=10000):
                page.goto(f"{base_url}/claims", wait_until="domcontentloaded")
            break
        except (PlaywrightError, RuntimeError):
            if attempt == 2:
                raise
    live_status = page.locator(".claims-list-live-status")
    expect(live_status).to_contain_text(f"{expected_total} klaim", timeout=10000)
    rows = page.locator('tbody tr:not(:has(td[colspan]))')
    expect(rows).to_have_count(expected_total, timeout=10000)


def main():
    parser = argparse.ArgumentParser(description="Smoke test ClaimsList and failed-claim retry UI")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    claims = [
        {
            "claim_id": "SMOKE-HIGH-OLD",
            "patient_id": "PAT-HIGH-OLD",
            "provider_id": "FAC-HIGH-OLD",
            "doctor_id": "DR-HIGH-OLD",
            "diagnosis_primary": "I10",
            "diagnosis_secondary": "",
            "procedure_codes": "",
            "severity_level": 2,
            "cost_claimed": 1100000,
            "length_of_stay": 2,
            "admission_date": "2026-09-01",
            "discharge_date": "2026-09-03",
            "medication_json": "[]",
            "referral_json": None,
            "received_at": "2026-09-13T10:00:00+00:00",
            "analysis_started_at": "2026-09-13T10:30:00+00:00",
            "analyzed_at": "2026-09-13T12:00:00+00:00",
            "queue_sequence": 30,
            "status": "review_required",
            "risk_score": 90,
            "priority_tier": "high",
            "human_decision": None,
            "analysis_attempts": 1,
            "last_analysis_error": None,
        },
        {
            "claim_id": CLAIM_ID,
            "patient_id": "PAT-SMOKE",
            "provider_id": "FAC-SMOKE",
            "doctor_id": "DR-SMOKE",
            "diagnosis_primary": "I10",
            "diagnosis_secondary": "",
            "procedure_codes": "",
            "severity_level": 2,
            "cost_claimed": 1250000,
            "length_of_stay": 3,
            "admission_date": "2026-09-01",
            "discharge_date": "2026-09-04",
            "medication_json": "[]",
            "referral_json": None,
            "received_at": "2026-09-13T10:00:00+00:00",
            "queue_sequence": 10,
            "status": "failed",
            "risk_score": 82,
            "priority_tier": "high",
            "human_decision": None,
            "analysis_attempts": 3,
            "last_analysis_error": "secret orchestrator stack trace",
        },
        {
            "claim_id": "SMOKE-MEDIUM",
            "patient_id": "PAT-MEDIUM",
            "provider_id": "FAC-MEDIUM",
            "doctor_id": "DR-MEDIUM",
            "diagnosis_primary": "E11",
            "diagnosis_secondary": "",
            "procedure_codes": "",
            "severity_level": 2,
            "cost_claimed": 900000,
            "length_of_stay": 2,
            "admission_date": "2026-09-02",
            "discharge_date": "2026-09-04",
            "medication_json": "[]",
            "referral_json": None,
            "received_at": "2026-09-09T10:00:00+00:00",
            "queue_sequence": 20,
            "status": "scanning",
            "risk_score": 60,
            "priority_tier": "medium",
            "human_decision": None,
            "analysis_attempts": 1,
            "last_analysis_error": None,
        },
        {
            "claim_id": "SMOKE-LOW",
            "patient_id": "PAT-LOW",
            "provider_id": "FAC-LOW",
            "doctor_id": "DR-LOW",
            "diagnosis_primary": "J10",
            "diagnosis_secondary": "",
            "procedure_codes": "",
            "severity_level": 1,
            "cost_claimed": 400000,
            "length_of_stay": 1,
            "admission_date": "2026-09-03",
            "discharge_date": "2026-09-04",
            "medication_json": "[]",
            "referral_json": None,
            "received_at": "2026-09-08T10:00:00+00:00",
            "queue_sequence": 40,
            "status": "processed",
            "risk_score": 20,
            "priority_tier": "low",
            "human_decision": None,
            "analysis_attempts": 1,
            "last_analysis_error": None,
        },
    ]
    claims_by_id = {item["claim_id"]: item for item in claims}
    retry_processed = {"value": False}
    initial_list_failure = {"value": False, "failed": False}

    list_requests = []
    analyze_requests = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="id-ID")
        console_errors = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))

        def route_api(route):
            request = route.request
            parsed = urlparse(request.url)
            query = parse_qs(parsed.query)

            if parsed.path == "/api/claims" and request.method == "GET":
                list_requests.append(query)
                if initial_list_failure["value"]:
                    initial_list_failure["failed"] = True
                    route.fulfill(status=503, json={"detail": "smoke outage"})
                    return
                items = claims
                if query.get("status"):
                    items = [item for item in claims if item["status"] == query["status"][0]]
                if query.get("tier"):
                    items = [item for item in items if item["priority_tier"] == query["tier"][0]]
                if query.get("q"):
                    needle = query["q"][0].lower()
                    items = [item for item in items if needle in " ".join(
                        str(item.get(field, "")) for field in ("claim_id", "patient_id", "provider_id", "diagnosis_primary")
                    ).lower()]
                if query.get("received_from"):
                    items = [item for item in items if item["received_at"][:10] >= query["received_from"][0]]
                if query.get("received_to"):
                    items = [item for item in items if item["received_at"][:10] <= query["received_to"][0]]
                if query.get("admission_from"):
                    items = [item for item in items if item["admission_date"] >= query["admission_from"][0]]
                if query.get("admission_to"):
                    items = [item for item in items if item["admission_date"] <= query["admission_to"][0]]
                sort = query.get("sort", ["priority"])[0]
                tier_order = {"high": 0, "medium": 1, "low": 2}
                if sort == "risk_asc":
                    items = sorted(items, key=lambda item: item["risk_score"])
                elif sort == "risk_desc":
                    items = sorted(items, key=lambda item: item["risk_score"], reverse=True)
                elif sort == "queue":
                    items = sorted(items, key=lambda item: item["queue_sequence"])
                elif sort == "id":
                    items = sorted(items, key=lambda item: item["claim_id"])
                else:
                    items = sorted(items, key=lambda item: (
                        tier_order.get(item["priority_tier"], 3),
                        item["received_at"],
                        item["queue_sequence"],
                    ))
                route.fulfill(status=200, json={"total": len(items), "items": items, "skip": 0, "limit": 25})
                return

            if parsed.path == "/api/analytics/dashboard" and request.method == "GET":
                route.fulfill(status=200, json={"total_claims": len(claims)})
                return

            if parsed.path.endswith(f"/{CLAIM_ID}/decision") and request.method == "GET":
                route.fulfill(status=200, json={"status": "no_decision"})
                return

            if parsed.path == "/api/health" and request.method == "GET":
                route.fulfill(status=200, json={"status": "ok"})
                return

            if parsed.path.startswith("/api/claims/") and request.method == "GET" and parsed.path.count("/") == 3:
                claim_id = parsed.path.rsplit("/", 1)[-1]
                route.fulfill(status=200, json=claims_by_id[claim_id])
                return

            if parsed.path == f"/api/claims/{CLAIM_ID}/analysis" and request.method == "GET":
                if retry_processed["value"]:
                    route.fulfill(status=200, json={
                        "status": "analyzed",
                        "analysis_version": 6,
                        "result": {
                            "analysis_version": 6,
                            "risk": {"total_score": 12, "priority_tier": "low"},
                            "explanation": {"recommended_action": "low_priority", "generated_by": "smoke"},
                        },
                    })
                else:
                    route.fulfill(status=200, json={"status": "not_analyzed"})
                return

            if parsed.path == "/api/claims/analyze" and request.method == "POST":
                analyze_requests.append(query)
                if query.get("retry") == ["true"]:
                    retry_processed["value"] = True
                    claims_by_id[CLAIM_ID].update({
                        "status": "processed",
                        "risk_score": 12,
                        "priority_tier": "low",
                        "analysis_attempts": 4,
                        "last_analysis_error": None,
                        "analysis_started_at": "2026-09-13T10:15:00+00:00",
                        "analyzed_at": "2026-09-13T10:45:00+00:00",
                    })
                    route.fulfill(status=200, json={
                        "status": "already_processed",
                        "claim_id": CLAIM_ID,
                    })
                    return
                route.fulfill(status=200, json={
                    "status": "failed",
                    "claim_id": CLAIM_ID,
                    "retry_available": True,
                    "message": "Analisis sebelumnya gagal. Kirim retry=true untuk mencoba lagi.",
                    "last_analysis_error": claims_by_id[CLAIM_ID]["last_analysis_error"],
                })
                return

            route.fulfill(status=404, json={"detail": "unmocked API route"})

        page.route("**/api/**", route_api)
        page.goto(f"{args.base_url}/claims")
        page.wait_for_function("""() => {
            const text = document.querySelector('.claims-list-live-status')?.textContent || ''
            const rows = [...document.querySelectorAll('tbody tr')]
            return text.includes('4 klaim') && rows.some(row => row.textContent.includes('Sedang diperiksa'))
        }""")

        live_status = page.locator(".claims-list-live-status")
        expect(live_status).to_have_attribute("role", "status")
        expect(live_status).to_have_attribute("aria-live", "polite")
        expect(live_status).to_contain_text("4 klaim")
        freshness = page.locator(".data-freshness")
        expect(freshness).to_have_attribute("role", "status")
        expect(freshness).to_have_attribute("aria-live", "polite")
        expect(freshness).to_contain_text("Data klaim sudah diperbarui.")

        claim_row = page.locator("tbody tr").filter(has_text=CLAIM_ID)
        expect(claim_row).to_be_visible()
        expect(claim_row.get_by_text("Pemeriksaan belum berhasil", exact=True)).to_be_visible()
        expect(page.get_by_text("Pemeriksaan belum berhasil. Silakan ulangi pemeriksaan.", exact=True)).to_be_visible()
        expect(page.get_by_text("secret orchestrator stack trace", exact=True)).to_have_count(0)
        assert list_requests[-1].get("sort") == ["priority"]
        rows = page.locator('tbody tr:not(:has(td[colspan]))')
        expect(rows).to_have_count(4)
        row_ids = [rows.nth(index).inner_text().splitlines()[0].strip() for index in range(4)]
        assert row_ids == [
            CLAIM_ID, "SMOKE-HIGH-OLD", "SMOKE-MEDIUM", "SMOKE-LOW"
        ]
        for label in ("Perlu ditinjau petugas", "Pemeriksaan belum berhasil", "Sedang diperiksa", "Pemeriksaan selesai"):
            expect(page.locator("tbody")).to_contain_text(label)

        filter_labels = (
            "Cari klaim",
            "Saring berdasarkan status",
            "Saring berdasarkan prioritas",
            "Tanggal klaim mulai",
            "Tanggal klaim sampai",
            "Tanggal masuk mulai",
            "Tanggal masuk sampai",
            "Urutkan daftar klaim",
        )
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(f"{args.base_url}/claims")
            for label in filter_labels:
                control = page.get_by_label(label)
                assert control.evaluate("element => element.getBoundingClientRect().height") >= 44, (width, label)
            refresh = page.get_by_role("button", name="Muat ulang")
            assert refresh.evaluate("element => element.getBoundingClientRect().height") >= 44, width
            for name in ("Sebelumnya", "Berikutnya"):
                pagination = page.get_by_role("button", name=name)
                assert pagination.evaluate("element => element.getBoundingClientRect().height") >= 44, (width, name)
            claim_link = page.get_by_role("link", name=f"Buka klaim {CLAIM_ID}")
            assert claim_link.evaluate("element => element.getBoundingClientRect().height") >= 44, width
            for name in ("Dashboard Utama", "Daftar Klaim", "Pemantauan Sistem", "Evaluasi Ketepatan", "Input Klaim"):
                nav_link = page.get_by_role("link", name=name)
                assert nav_link.evaluate("element => element.getBoundingClientRect().height") >= 44, (width, name)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width

        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(f"{args.base_url}/claims?initial-error=1")

        assert page.locator('a[href="/"]').get_attribute("href") == "/"
        page.goto(f"{args.base_url}/")
        page.wait_for_function("document.activeElement && document.activeElement.id === 'main-content'")
        assert page.locator('a[href="/claims"]').get_attribute("href") == "/claims"
        page.goto(f"{args.base_url}/claims")
        page.goto(f"{args.base_url}/claims?source=dashboard")
        page.wait_for_load_state("networkidle")
        search = page.get_by_label("Cari klaim")
        search.focus()
        assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "Cari klaim"

        with page.expect_response(lambda response: "q=SMOKE-LOW" in response.url):
            search.fill("SMOKE-LOW")
        page.wait_for_function("new URL(window.location.href).searchParams.get('q') === 'SMOKE-LOW'")
        assert parse_qs(urlparse(page.url).query) == {"source": ["dashboard"], "q": ["SMOKE-LOW"]}
        expect(page.locator('tbody tr:not(:has(td[colspan]))')).to_have_count(1)
        expect(page.locator("tbody")).to_contain_text("SMOKE-LOW")

        page.goto(f"{args.base_url}/claims?sort=risk_asc")
        expect(page.get_by_label("Urutkan daftar klaim")).to_have_value("risk_asc")
        risk_rows = page.locator('tbody tr:not(:has(td[colspan]))')
        expect(risk_rows).to_have_count(4)
        assert [risk_rows.nth(index).inner_text().splitlines()[0].strip() for index in range(4)] == [
            "SMOKE-LOW", "SMOKE-MEDIUM", CLAIM_ID, "SMOKE-HIGH-OLD"
        ]

        page.goto(f"{args.base_url}/claims")
        with page.expect_response(lambda response: "sort=risk_desc" in response.url):
            page.get_by_label("Urutkan daftar klaim").select_option("risk_desc")
        page.wait_for_function("new URL(window.location.href).searchParams.get('sort') === 'risk_desc'")
        expect(page.get_by_label("Urutkan daftar klaim")).to_have_value("risk_desc")
        assert parse_qs(urlparse(page.url).query) == {"sort": ["risk_desc"]}
        sorted_rows = page.locator('tbody tr:not(:has(td[colspan]))')
        expect(sorted_rows).to_have_count(4)
        assert [sorted_rows.nth(index).inner_text().splitlines()[0].strip() for index in range(4)] == [
            "SMOKE-HIGH-OLD", CLAIM_ID, "SMOKE-MEDIUM", "SMOKE-LOW"
        ]

        page.goto(f"{args.base_url}/claims?source=dashboard")
        with page.expect_response(lambda response: "tier=high" in response.url):
            priority_filter = page.get_by_label("Saring berdasarkan prioritas")
            priority_filter.focus()
            priority_filter.select_option("high")
        page.wait_for_function("new URL(window.location.href).searchParams.get('tier') === 'high'")
        assert page.evaluate("document.activeElement?.getAttribute('aria-label')") == "Saring berdasarkan prioritas"
        assert parse_qs(urlparse(page.url).query) == {"source": ["dashboard"], "tier": ["high"]}, page.url
        expect(page.locator('tbody tr:not(:has(td[colspan]))')).to_have_count(2)

        page.goto(f"{args.base_url}/claims?tier=high")
        high_rows = page.locator('tbody tr:not(:has(td[colspan]))')
        expect(high_rows).to_have_count(2)
        assert list_requests[-1].get("tier") == ["high"]
        expect(page.locator("tbody")).not_to_contain_text("SMOKE-MEDIUM")
        expect(page.locator("tbody")).not_to_contain_text("SMOKE-LOW")

        page.goto(f"{args.base_url}/claims")
        rows = page.locator('tbody tr:not(:has(td[colspan]))')
        expect(rows).to_have_count(4)

        with page.expect_response(lambda response: "status=failed" in response.url):
            page.get_by_label("Saring berdasarkan status").select_option("failed")
        assert list_requests[-1].get("status") == ["failed"]
        expect(rows).to_have_count(1)

        with page.expect_response(lambda response: "received_from=2026-09-14" in response.url):
            page.get_by_label("Tanggal klaim mulai").fill("2026-09-14")
        expect(rows).to_have_count(0)
        with page.expect_response(lambda response: "received_from=2026-09-11" in response.url):
            page.get_by_label("Tanggal klaim mulai").fill("2026-09-11")
        expect(rows).to_have_count(1)
        with page.expect_response(lambda response: "received_to=2026-09-13" in response.url):
            page.get_by_label("Tanggal klaim sampai").fill("2026-09-13")
        with page.expect_response(lambda response: "admission_from=2026-09-02" in response.url):
            page.get_by_label("Tanggal masuk mulai").fill("2026-09-02")
        with page.expect_response(lambda response: "admission_to=2026-09-04" in response.url):
            page.get_by_label("Tanggal masuk sampai").fill("2026-09-04")
        assert parse_qs(urlparse(page.url).query) == {
            "status": ["failed"],
            "received_from": ["2026-09-11"],
            "received_to": ["2026-09-13"],
            "admission_from": ["2026-09-02"],
            "admission_to": ["2026-09-04"],
        }

        with page.expect_response(lambda response: response.url.endswith("/api/claims?skip=0&limit=25&sort=priority")):
            page.get_by_role("button", name="Reset Filter").click()
        expect(rows).to_have_count(4)

        page.goto(
            f"{args.base_url}/claims?status=review_required&received_from=2026-09-13"
            "&received_to=2026-09-13&admission_from=2026-09-01&admission_to=2026-09-03"
        )
        expect(page.get_by_label("Saring berdasarkan status")).to_have_value("review_required")
        expect(page.get_by_label("Tanggal klaim mulai")).to_have_value("2026-09-13")
        expect(page.get_by_label("Tanggal klaim sampai")).to_have_value("2026-09-13")
        expect(page.get_by_label("Tanggal masuk mulai")).to_have_value("2026-09-01")
        expect(page.get_by_label("Tanggal masuk sampai")).to_have_value("2026-09-03")

        page.goto(f"{args.base_url}/claims")
        page.get_by_role("link", name=f"Buka klaim {CLAIM_ID}").click()
        page.wait_for_url(f"**/investigate/{CLAIM_ID}")
        expect(page.get_by_role("alert").get_by_text("Pemeriksaan belum berhasil. Silakan ulangi pemeriksaan.", exact=True)).to_be_visible()
        expect(page.get_by_text("secret orchestrator stack trace", exact=True)).to_have_count(0)
        expect(page.get_by_role("button", name="Ulangi Pemeriksaan")).to_be_visible()

        with page.expect_response(lambda response: "retry=true" in response.url and response.status == 200):
            page.get_by_role("button", name="Ulangi Pemeriksaan").click()
        page.wait_for_url(f"**/assessment/{CLAIM_ID}")
        assert analyze_requests[0].get("retry") != ["true"]
        assert analyze_requests[-1].get("retry") == ["true"]
        goto_claims_and_wait(page, args.base_url, expected_total=4)
        processed_row = page.locator("tbody tr").filter(has_text=CLAIM_ID)
        expect(processed_row).to_contain_text("Pemeriksaan selesai")
        expect(processed_row.get_by_text("Pemeriksaan selesai", exact=True)).to_be_visible()
        expect(processed_row).to_contain_text("Menunggu keputusan petugas")
        expect(processed_row).to_contain_text("45,0 menit")
        review_row = page.locator("tbody tr").filter(has_text="SMOKE-HIGH-OLD")
        expect(review_row).to_contain_text("2,0 jam")
        claims.append({
            **claims_by_id["SMOKE-LOW"],
            "claim_id": "SMOKE-VERIFIED",
            "status": "verified",
            "human_decision": "Verified Valid",
            "received_at": "2026-09-13T10:00:00+00:00",
            "analyzed_at": "2026-09-13T11:00:00+00:00",
            "verified_at": "2026-09-13T13:00:00+00:00",
        })
        goto_claims_and_wait(page, args.base_url, expected_total=5)
        verified_row = page.locator("tbody tr").filter(has_text="SMOKE-VERIFIED")
        expect(verified_row).to_contain_text("3,0 jam")
        page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
        axe_result = page.evaluate("async () => await axe.run()")
        assert not [(violation["id"], violation["impact"]) for violation in axe_result["violations"]]

        page.close()
        error_context = browser.new_context(locale="id-ID")
        page = error_context.new_page()
        error_console_errors = []
        page.on(
            "console",
            lambda message: error_console_errors.append(message.text)
            if message.type == "error" and message.text != EXPECTED_503_CONSOLE_ERROR
            else None,
        )
        page.on("pageerror", lambda error: error_console_errors.append(str(error)))
        page.route("**/api/**", route_api)
        initial_list_failure.update({"value": True, "failed": False})
        page.goto(f"{args.base_url}/claims")
        expect(page.locator(".data-freshness")).to_contain_text("Data klaim belum berhasil diperbarui.")
        expect(page.get_by_role("button", name="Muat ulang")).to_be_visible()
        initial_list_failure["value"] = False
        page.get_by_role("button", name="Muat ulang").click()
        expect(page.locator(".claims-list-live-status")).to_contain_text("5 klaim")
        assert not error_console_errors, error_console_errors
        assert not console_errors, console_errors
        error_context.close()
        browser.close()


if __name__ == "__main__":
    main()
