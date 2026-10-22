"""Native Playwright smoke test for keyboard access to Assessment disclosures."""

import argparse
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


CLAIM_ID = "SMOKE-ASSESSMENT"
ANALYSIS_RETRY_ID = "SMOKE-ANALYSIS-RETRY"
DECISION_RETRY_ID = "SMOKE-DECISION-RETRY"
REPEAT_EVIDENCE_ID = "SMOKE-REPEAT-EVIDENCE"


def minimal_analysis():
    return {
        "analysis_version": 6,
        "risk": {"total_score": 40, "priority_tier": "medium", "breakdown": {}, "evidence": []},
        "explanation": {"narrative_id": "Ringkasan pemeriksaan.", "qa_panel": {}, "recommended_action": "review_when_available"},
    }


def main():
    parser = argparse.ArgumentParser(description="Smoke test Assessment keyboard disclosure")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    decision_state = {"decision": "Verified Valid", "verified_at": "2026-09-13T10:00:00+00:00"}
    decision_save_state = {"attempts": 0}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="id-ID")
        console_errors = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" and "status of 503" not in message.text else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))

        def route_api(route):
            parsed = urlparse(route.request.url)
            if parsed.path == f"/api/claims/{CLAIM_ID}/analysis":
                route.fulfill(status=200, json={
                    "status": "analyzed",
                    "result": {
                        "analysis_version": 6,
                        "risk": {
                            "total_score": 80,
                            "priority_tier": "high",
                            "breakdown": {},
                            "evidence": [],
                        },
                        "explanation": {
                            "narrative_id": "Ringkasan pemeriksaan.",
                            "qa_panel": {},
                            "recommended_action": "verify_immediately",
                        },
                        "clinical": {"evidence_text": "SECRET_PERSISTED_EXCEPTION"},
                        "financial": {"evidence_text": "SECRET_PERSISTED_EXCEPTION"},
                        "fraud": {
                            "evidence_text": "[fraud-agent internal-error] SECRET_PERSISTED_EXCEPTION",
                            "similar_claims": [{
                                "claim_id": "SIMILAR-001",
                                "diagnosis_primary": "I10",
                                "cost_claimed": 100000,
                                "similarity": 0.92,
                                "code_similarity": 0.8,
                                "cost_proximity": 0.95,
                                "same_provider": True,
                                "same_patient": False,
                                "days_apart": 3,
                            }],
                        },
                        "review": {"reasoning_narrative": "Traceback (most recent call last): RuntimeError: SECRET_PERSISTED_EXCEPTION"},
                    },
                })
                return
            if parsed.path == f"/api/claims/{REPEAT_EVIDENCE_ID}/analysis":
                route.fulfill(status=200, json={
                    "status": "analyzed",
                    "result": {
                        **minimal_analysis(),
                        "fraud": {
                            "repeat_billing_flag": True,
                            "repeat_billing_matched_claim_id": "REPEAT-REFERENCE-001",
                            "similar_claims": [],
                        },
                    },
                })
                return
            if parsed.path == f"/api/claims/{CLAIM_ID}/decision" and route.request.method == "GET":
                route.fulfill(status=200, json={
                    "status": "decided",
                    "decision": decision_state["decision"],
                    "reviewer": "BPJS-VERIFIER-01",
                    "verified_at": decision_state["verified_at"],
                })
                return
            if parsed.path == f"/api/claims/{REPEAT_EVIDENCE_ID}/decision":
                route.fulfill(status=200, json={"status": "no_decision"})
                return
            if parsed.path == f"/api/claims/{CLAIM_ID}/decision" and route.request.method == "POST":
                decision_save_state["attempts"] += 1
                decision_state["decision"] = route.request.post_data_json["decision"]
                if decision_save_state["attempts"] == 1:
                    route.fulfill(status=503, json={"error_code": "dependency_unavailable"})
                    return
                route.fulfill(status=200, json={
                    "status": "success",
                    "verified_at": decision_state["verified_at"],
                })
                return
            route.continue_()

        page.route("**/api/**", route_api)
        page.goto(f"{args.base_url}/assessment/{CLAIM_ID}")
        page.wait_for_load_state("networkidle")
        assert "SECRET_PERSISTED_EXCEPTION" not in page.locator("body").inner_text()

        toggle = page.get_by_role("button", name="Buka rincian faktor kemiripan untuk klaim SIMILAR-001")
        expect(toggle).to_be_visible()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        toggle.focus()
        toggle_height = page.evaluate("document.activeElement.getBoundingClientRect().height")
        assert toggle_height >= 44, toggle_height
        page.keyboard.press("Enter")
        expect(toggle).to_have_attribute("aria-expanded", "true")
        expect(page.locator("#similar-claim-SIMILAR-001")).to_be_visible()
        page.keyboard.press("Space")
        expect(toggle).to_have_attribute("aria-expanded", "false")
        qa_summary = page.get_by_text("Kenapa klaim ini mendapat prioritas ini?", exact=True)
        qa_summary.focus()
        qa_summary_height = page.evaluate("document.activeElement.getBoundingClientRect().height")
        assert qa_summary_height >= 44, qa_summary_height
        outline = page.evaluate("""() => {
            const style = getComputedStyle(document.activeElement)
            return {style: style.outlineStyle, width: parseFloat(style.outlineWidth)}
        }""")
        assert outline["style"] != "none" and outline["width"] >= 2, outline
        expect(page.get_by_role("button", name="Ubah Keputusan")).to_be_visible()
        page.get_by_role("button", name="Ubah Keputusan").click()
        decision_options = page.locator("label.assessment-decision-option")
        expect(decision_options).to_have_count(4)
        expect(page.get_by_role("group", name="Keputusan Petugas Verifier")).to_be_visible()
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 900})
            for index in range(decision_options.count()):
                height = decision_options.nth(index).evaluate("element => element.getBoundingClientRect().height")
                assert height >= 44, (width, index, height)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
        page.get_by_role("radio", name="Perlu Peninjauan Lebih Lanjut").check()
        with page.expect_response(lambda response: response.url.endswith(f"/api/claims/{CLAIM_ID}/decision") and response.request.method == "POST" and response.status == 503):
            page.get_by_role("button", name="Simpan Keputusan").click()
        expect(page.get_by_role("alert")).to_contain_text("Keputusan belum tersimpan")
        expect(page.get_by_role("button", name="Coba simpan lagi")).to_be_visible()
        expect(page.get_by_role("radio", name="Perlu Peninjauan Lebih Lanjut")).to_be_checked()
        with page.expect_response(lambda response: response.url.endswith(f"/api/claims/{CLAIM_ID}/decision") and response.request.method == "POST" and response.status == 200):
            page.get_by_role("button", name="Coba simpan lagi").click()
        expect(page.get_by_text("Keputusan Berhasil Disimpan", exact=True)).to_be_visible()
        expect(page.get_by_text("Perlu Peninjauan Lebih Lanjut", exact=True)).to_be_visible()

        repeat_evidence_page = browser.new_page(locale="id-ID")
        repeat_evidence_page.route("**/api/**", route_api)
        repeat_evidence_page.goto(f"{args.base_url}/assessment/{REPEAT_EVIDENCE_ID}")
        expect(repeat_evidence_page.get_by_text("Klaim berulang terdeteksi: REPEAT-REFERENCE-001", exact=True)).to_be_visible()
        repeat_evidence_page.close()

        page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
        axe_result = page.evaluate("async () => await axe.run()")
        violations = [(violation["id"], violation["impact"]) for violation in axe_result["violations"]]
        assert not violations, violations
        assert not console_errors, console_errors

        analysis_retry_page = browser.new_page(locale="id-ID")
        analysis_retry_state = {"attempts": 0, "reset_calls": 0}

        def analysis_retry_route(route):
            parsed = urlparse(route.request.url)
            if parsed.path == f"/api/claims/{ANALYSIS_RETRY_ID}/analysis":
                analysis_retry_state["attempts"] += 1
                if analysis_retry_state["attempts"] <= 2:
                    route.fulfill(status=503, json={"error_code": "dependency_unavailable"})
                else:
                    route.fulfill(status=200, json={"status": "analyzed", "result": minimal_analysis()})
                return
            if parsed.path == f"/api/claims/{ANALYSIS_RETRY_ID}" and route.request.method == "DELETE":
                analysis_retry_state["reset_calls"] += 1
                route.fulfill(status=200, json={"status": "success"})
                return
            if parsed.path == f"/api/claims/{ANALYSIS_RETRY_ID}/decision":
                route.fulfill(status=200, json={"status": "no_decision"})
                return
            route.continue_()

        analysis_retry_page.route("**/api/**", analysis_retry_route)
        analysis_retry_page.goto(f"{args.base_url}/assessment/{ANALYSIS_RETRY_ID}")
        expect(analysis_retry_page.get_by_role("alert")).to_contain_text("Hasil pemeriksaan belum dapat dimuat")
        expect(analysis_retry_page.get_by_role("button", name="Coba muat lagi")).to_be_visible()
        assert "Silakan jalankan investigasi terlebih dahulu" not in analysis_retry_page.locator("body").inner_text()
        with analysis_retry_page.expect_response(lambda response: response.url.endswith(f"/api/claims/{ANALYSIS_RETRY_ID}/analysis") and response.status == 200):
            analysis_retry_page.get_by_role("button", name="Coba muat lagi").click()
        expect(analysis_retry_page.get_by_role("heading", name="Hasil Pemeriksaan Klaim")).to_be_visible()
        assert analysis_retry_state["reset_calls"] == 0
        analysis_retry_page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
        assert not analysis_retry_page.evaluate("async () => await axe.run()")['violations']
        analysis_retry_page.close()

        decision_retry_page = browser.new_page(locale="id-ID")
        decision_retry_state = {"attempts": 0}

        def decision_retry_route(route):
            parsed = urlparse(route.request.url)
            if parsed.path == f"/api/claims/{DECISION_RETRY_ID}/analysis":
                route.fulfill(status=200, json={"status": "analyzed", "result": minimal_analysis()})
                return
            if parsed.path == f"/api/claims/{DECISION_RETRY_ID}/decision":
                decision_retry_state["attempts"] += 1
                if decision_retry_state["attempts"] <= 2:
                    route.fulfill(status=503, json={"error_code": "dependency_unavailable"})
                else:
                    route.fulfill(status=200, json={"status": "decided", "decision": "Verified Valid", "reviewer": "BPJS-VERIFIER-01"})
                return
            route.continue_()

        decision_retry_page.route("**/api/**", decision_retry_route)
        decision_retry_page.goto(f"{args.base_url}/assessment/{DECISION_RETRY_ID}")
        expect(decision_retry_page.get_by_role("alert")).to_contain_text("Riwayat keputusan belum dapat dimuat")
        expect(decision_retry_page.get_by_role("button", name="Muat keputusan lagi")).to_be_visible()
        with decision_retry_page.expect_response(lambda response: response.url.endswith(f"/api/claims/{DECISION_RETRY_ID}/decision") and response.status == 200):
            decision_retry_page.get_by_role("button", name="Muat keputusan lagi").click()
        expect(decision_retry_page.get_by_text("Keputusan Berhasil Disimpan", exact=True)).to_be_visible()
        decision_retry_page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
        assert not decision_retry_page.evaluate("async () => await axe.run()")['violations']
        decision_retry_page.close()
        browser.close()


if __name__ == "__main__":
    main()
