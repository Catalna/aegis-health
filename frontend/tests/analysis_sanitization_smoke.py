"""Browser regression for analysis sanitization across cache and SSE paths."""

import argparse
import json
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


MARKER = "SECRET_PERSISTED_EXCEPTION"
RAW_MARKER = "RAW_EXCEPTION_MARKER"


def analysis_payload():
    return {
        "analysis_version": 6,
        "clinical": {"evidence_text": MARKER, "rule_flags": [], "evidence_source": "rule_engine"},
        "financial": {"evidence_text": RAW_MARKER, "deviation_pct": 0, "anomaly_score": 0, "shap_top_features": []},
        "fraud": {"evidence_text": f"Traceback: {MARKER}", "similar_claims": [], "similarity_max_score": 0},
        "review": {"reasoning_narrative": f"InternalError: {MARKER}", "reasoning_source": "rule_fallback"},
        "risk": {
            "total_score": 10,
            "priority_tier": "low",
            "breakdown": {},
            "evidence": [{"evidence_id": "E-1", "source_family": "clinical_rule", "signal_type": "flag", "explanation": RAW_MARKER}],
        },
        "explanation": {
            "narrative_id": RAW_MARKER,
            "ranked_reasons": [MARKER],
            "recommended_action": "low_priority",
            "qa_panel": {
                "why_top_priority": RAW_MARKER,
                "strongest_evidence": MARKER,
                "most_similar_claim": RAW_MARKER,
                "is_this_fraud": MARKER,
            },
        },
    }


def sse_body():
    payload = analysis_payload()
    events = [
        ("phase1_complete", {key: payload[key] for key in ("clinical", "financial", "fraud")}),
        ("phase2_complete", {"review": payload["review"]}),
        ("phase3_complete", {"risk": payload["risk"]}),
        ("phase4_complete", {"explanation": payload["explanation"]}),
        ("done", {}),
    ]
    return "".join(
        f"event: {event}\ndata: {json.dumps(data)}\n\n" for event, data in events
    )


def main():
    parser = argparse.ArgumentParser(description="Smoke test analysis sanitization in cache and SSE")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        storage_page = browser.new_page(locale="id-ID")
        storage_errors = []
        storage_page.on("console", lambda message: storage_errors.append(message.text) if message.type == "error" else None)
        storage_page.on("pageerror", lambda error: storage_errors.append(str(error)))
        storage_value = json.dumps(analysis_payload())
        storage_page.add_init_script(
            f"sessionStorage.setItem('result_SMOKE-STORAGE', {json.dumps(storage_value)});"
        )

        def storage_route(route):
            parsed = urlparse(route.request.url)
            if parsed.path == "/api/claims/SMOKE-STORAGE/decision":
                route.fulfill(status=200, json={"status": "not_decided"})
                return
            route.continue_()

        storage_page.route("**/api/**", storage_route)
        storage_page.goto(f"{args.base_url}/assessment/SMOKE-STORAGE")
        expect(storage_page.get_by_role("heading", name="Hasil Pemeriksaan Klaim")).to_be_visible()
        storage_page.wait_for_function(
            "() => !sessionStorage.getItem('result_SMOKE-STORAGE').includes('SECRET_PERSISTED_EXCEPTION') && !sessionStorage.getItem('result_SMOKE-STORAGE').includes('RAW_EXCEPTION_MARKER')"
        )
        assert MARKER not in storage_page.locator("body").inner_text()
        assert RAW_MARKER not in storage_page.locator("body").inner_text()
        assert not storage_errors, storage_errors

        sse_page = browser.new_page(locale="id-ID")
        sse_errors = []
        sse_page.on("console", lambda message: sse_errors.append(message.text) if message.type == "error" else None)
        sse_page.on("pageerror", lambda error: sse_errors.append(str(error)))

        def sse_route(route):
            parsed = urlparse(route.request.url)
            if parsed.path == "/api/claims/SMOKE-SSE":
                route.fulfill(status=200, json={
                    "claim_id": "SMOKE-SSE",
                    "patient_id": "PATIENT-1",
                    "provider_id": "FACILITY-1",
                    "doctor_id": "DOCTOR-1",
                    "diagnosis_primary": "I10",
                    "diagnosis_secondary": "",
                    "procedure_codes": "",
                    "severity_level": 1,
                    "cost_claimed": 100,
                    "length_of_stay": 1,
                })
                return
            if parsed.path == "/api/claims/analyze":
                route.fulfill(status=200, json={"task_id": "SMOKE-TASK", "status": "started"})
                return
            if parsed.path == "/api/stream/SMOKE-TASK":
                route.fulfill(status=200, headers={"Content-Type": "text/event-stream"}, body=sse_body())
                return
            if parsed.path == "/api/claims/SMOKE-SSE/decision":
                route.fulfill(status=200, json={"status": "not_decided"})
                return
            route.continue_()

        sse_page.route("**/api/**", sse_route)
        sse_page.goto(f"{args.base_url}/investigate/SMOKE-SSE?rerun=1")
        see_results = sse_page.get_by_role("button", name="Lihat Hasil Pemeriksaan")
        expect(see_results).to_be_visible()
        sse_page.wait_for_function(
            "() => !sessionStorage.getItem('result_SMOKE-SSE').includes('SECRET_PERSISTED_EXCEPTION') && !sessionStorage.getItem('result_SMOKE-SSE').includes('RAW_EXCEPTION_MARKER')"
        )
        assert MARKER not in sse_page.locator("body").inner_text()
        assert RAW_MARKER not in sse_page.locator("body").inner_text()
        see_results.click()
        sse_page.wait_for_url("**/assessment/SMOKE-SSE")
        expect(sse_page.get_by_role("heading", name="Hasil Pemeriksaan Klaim")).to_be_visible()
        assert MARKER not in sse_page.locator("body").inner_text()
        assert RAW_MARKER not in sse_page.locator("body").inner_text()
        assert not sse_errors, sse_errors

        for page in (storage_page, sse_page):
            page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4/axe.min.js")
            axe_result = page.evaluate("async () => await axe.run()")
            violations = [(violation["id"], violation["impact"]) for violation in axe_result["violations"]]
            assert not violations, violations

        browser.close()


if __name__ == "__main__":
    main()
