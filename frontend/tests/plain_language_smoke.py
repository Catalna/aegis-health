import json

from playwright.sync_api import expect, sync_playwright


def main():
    payload = {
        "analysis_version": 6,
        "clinical": {
            "rule_flags": ["severity_med_mismatch"],
            "evidence_text": "Sinyal deterministik: severity_med_mismatch.",
            "evidence_source": "llm_local",
        },
        "financial": {
            "evidence_text": (
                "Claimed amount Rp 4,000,000 berbanding reimbursement benchmark model "
                "Rp 1,902,113 (deviasi +110.3%)."
            ),
            "shap_top_features": [],
        },
        "fraud": {"similar_claims": [], "evidence_text": "Tidak ada pola."},
        "review": {
            "reasoning_narrative": "[Penilaian analisis tambahan (mistral:7b)] Catatan tersedia.",
            "reasoning_source": "llm_direct",
        },
        "risk": {
            "total_score": 80,
            "priority_tier": "high",
            "breakdown": {"clinical_rule_flags": 3},
            "evidence": [],
        },
        "explanation": {
            "narrative_id": "Klaim perlu diperiksa lebih lanjut.",
            "recommended_action": "verify_immediately",
            "qa_panel": {
                "why_top_priority": "Nilai risiko tinggi.",
                "strongest_evidence": "Temuan tersedia.",
                "most_similar_claim": "Tidak ada.",
                "is_this_fraud": "Keputusan akhir berada pada petugas.",
            },
        },
    }
    forbidden = (
        "severity_med_mismatch",
        "mistral:7b",
        "Claimed amount",
        "reimbursement benchmark model",
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="id-ID")
        page.add_init_script(
            f"sessionStorage.setItem('result_PLAIN-SMOKE', {json.dumps(json.dumps(payload))});"
        )
        page.route(
            "**/api/claims/PLAIN-SMOKE/decision",
            lambda route: route.fulfill(status=200, json={"status": "not_decided"}),
        )
        page.goto("http://localhost:5173/assessment/PLAIN-SMOKE")
        expect(page.get_by_role("heading", name="Hasil Pemeriksaan Klaim")).to_be_visible()
        body = page.locator("body").inner_text()
        for term in forbidden:
            assert term not in body, term
        assert "Temuan berdasarkan aturan pemeriksaan" in body
        assert "Biaya yang diajukan" in body
        browser.close()
    print("plain language smoke passed")


if __name__ == "__main__":
    main()
