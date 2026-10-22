from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def test_assessment_uses_deterministic_evidence_support_label():
    assessment = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    language = (ROOT / "frontend/src/humanLanguage.js").read_text(encoding="utf-8")
    assert "COMPONENT_LABELS" in assessment
    assert "evidence_support" in language
    assert "Kekuatan dasar penilaian" in language


def test_dashboard_uses_financial_exposure_language():
    dashboard = (ROOT / "frontend/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
    assert "Perkiraan selisih biaya" in dashboard
    assert "Potential Financial Exposure" not in dashboard
    assert "Potential Savings" not in dashboard


def test_dashboard_api_exposes_additive_financial_exposure_key():
    api = (ROOT / "backend/app/api/main.py").read_text(encoding="utf-8")
    assert '"potential_financial_exposure"' in api


def test_p1_evaluation_api_exposes_versioned_artifact_route():
    api = (ROOT / "backend/app/api/main.py").read_text(encoding="utf-8")
    assert "_P1_EVAL_PATH" in api
    assert '"/api/ml/eval/p1"' in api


def test_ml_evaluation_page_uses_p1_ranking_metrics_and_limitations():
    page = (ROOT / "frontend/src/pages/MLEvaluation.jsx").read_text(encoding="utf-8")
    assert "average_precision" in page
    assert "delta_vs_p0_core" in page
    assert "Data contoh belum menggantikan pengujian di lapangan" in page


def test_investigation_disposes_sse_and_polling_on_unmount():
    page = (ROOT / "frontend/src/pages/Investigation.jsx").read_text(encoding="utf-8")
    assert "clearTimeout" in page
    assert "sse.close" in page
    assert "disposed" in page


def test_frontend_error_rendering_uses_allowlisted_error_categories():
    api = (ROOT / "frontend/src/api.js").read_text(encoding="utf-8")
    language = (ROOT / "frontend/src/humanLanguage.js").read_text(encoding="utf-8")
    claims = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    investigation = (ROOT / "frontend/src/pages/Investigation.jsx").read_text(encoding="utf-8")
    monitoring = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")

    for code in ("analysis_retryable", "validation_rejected", "dependency_unavailable"):
        assert code in language
    assert "safeErrorMessage" in claims
    assert "safeErrorMessage" in investigation
    assert "response?.data?.detail" not in investigation
    assert "pollError.message" not in investigation
    assert "secret" not in monitoring.lower()


def test_claims_list_labels_all_queue_lifecycle_statuses():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    for status in ("scanning", "review_required", "failed"):
        assert status in page


def test_claims_list_shows_queue_metadata_and_received_date_filters():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    for marker in ("received_at", "analysis_attempts", "last_analysis_error", "received_from", "received_to", "admission_from", "admission_to"):
        assert marker in page


def test_claims_list_defaults_to_verifier_priority_ordering():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "const sort = VALID_SORTS.includes(querySort) ? querySort : 'priority'" in page
    assert "value=\"priority\"" in page


def test_claims_list_uses_wcag_safe_score_red_and_dark_amber_lifecycle_text():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert "var(--risk-high-text)" in page
    assert "--risk-high-text: #b91c1c" in css
    assert "isReview ? 'var(--warning-text)'" in page


def test_claims_list_uses_darker_text_on_light_slate_lifecycle_badges():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "isReview ? 'var(--warning-text)' : 'var(--text-secondary)'" in page


def test_claims_list_review_badge_uses_light_amber_with_dark_foreground():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "isReview ? 'var(--risk-medium-bg)'" in page
    assert "isReview ? 'var(--warning-text)'" in page


def test_claims_list_uses_dark_red_background_for_failed_badge_contrast():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "isFailed ? 'var(--error-text)'" in page
    assert "isFailed ? 'white'" in page


def test_claims_list_uses_compliant_risk_badge_and_error_tokens():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert ".badge-high" in css
    assert "color: var(--risk-high-text)" in css
    assert "--risk-medium-text: #b45309" in css
    assert ".badge-medium" in css
    assert "color: var(--risk-medium-text)" in css
    assert "c.last_analysis_error ? 'var(--risk-high-text)'" in page


def test_claims_list_pending_badge_uses_wcag_safe_neutral_foreground():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "background: 'var(--bg-card-hover)', color: 'var(--text-secondary)'" in page


def test_ml_evaluation_starts_with_one_h1_and_uses_h2_for_metric_heading():
    page = (ROOT / "frontend/src/pages/MLEvaluation.jsx").read_text(encoding="utf-8")
    headings = re.findall(r"<h([1-6])(?:\s|>)", page)
    assert headings[:2] == ["1", "2"]
    assert headings.count("1") == 1
    assert '<h1 className="evaluation-title">' in page
    assert '<h2 id="evaluation-headline"' in page


def test_sidebar_brand_is_not_a_document_heading():
    app = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert '<div className="sidebar-brand-title">AEGIS</div>' in app
    assert ".sidebar-logo h1" not in css
    assert ".sidebar-brand-title" in css


def test_frontend_defines_semantic_warning_and_error_text_tokens():
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert "--warning-text: #b45309" in css
    assert "--error-text: #b91c1c" in css


def test_frontend_uses_dark_semantic_tokens_for_warning_and_error_text():
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    dashboard = (ROOT / "frontend/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
    claims = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    intake = (ROOT / "frontend/src/pages/ClaimIntake.jsx").read_text(encoding="utf-8")
    assessment = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    investigation = (ROOT / "frontend/src/pages/Investigation.jsx").read_text(encoding="utf-8")
    monitoring = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")

    assert "color: var(--error-text)" in css
    assert "color: var(--warning-text)" in css
    assert "var(--warning-text)" in dashboard
    assert "var(--error-text)" in claims
    assert "var(--error-text)" in intake
    assert "var(--warning-text)" in intake
    assert "var(--warning-text)" in assessment
    assert "var(--error-text)" in investigation
    assert "var(--warning-text)" in investigation
    assert "var(--error-text)" in monitoring


def test_sidebar_uses_router_links_for_navigation():
    app = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    assert "NavLink" in app
    assert "to={item.path}" in app
    assert "onClick={() => navigate(item.path)}" not in app


def test_primary_work_pages_have_semantic_page_headings():
    for filename in (
        "Dashboard.jsx",
        "ClaimsList.jsx",
        "Monitoring.jsx",
        "ClaimIntake.jsx",
        "Investigation.jsx",
        "Assessment.jsx",
    ):
        page = (ROOT / "frontend/src/pages" / filename).read_text(encoding="utf-8")
        assert re.search(r"<h1\b", page), filename


def test_queue_summary_uses_existing_claim_lifecycle_data():
    summary = (ROOT / "frontend/src/queueSummaryData.js").read_text(encoding="utf-8")
    for marker in ("pending", "scanning", "review_required", "received_at", "analysis_started_at", "analyzed_at", "verified_at"):
        assert marker in summary
    for filename in ("Dashboard.jsx", "Monitoring.jsx"):
        page = (ROOT / "frontend/src/pages" / filename).read_text(encoding="utf-8")
        assert "QueueSummary" in page
        assert "fetchQueueSummary" in page


def test_claims_and_monitoring_render_stale_data_refresh_states():
    component = (ROOT / "frontend/src/DataFreshness.jsx").read_text(encoding="utf-8")
    assert "Muat ulang" in component
    assert "stale" in component
    for filename in ("ClaimsList.jsx", "Monitoring.jsx"):
        page = (ROOT / "frontend/src/pages" / filename).read_text(encoding="utf-8")
        assert "DataFreshness" in page


def test_monitoring_neutral_status_badges_use_compliant_foreground():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    assert "color: status === 'ok' ? 'var(--accent-green)' : 'var(--text-secondary)'" in page
    assert "color: statusTextColor(status)" in page


def test_monitoring_health_badges_use_light_surfaces_and_dark_foregrounds():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert "const statusBadgeColors" in page
    assert "--risk-medium-bg: #fffbeb" in css
    assert "background: 'var(--risk-medium-bg)'" in page
    assert "color: 'var(--warning-text)'" in page
    assert "background: 'var(--risk-high-bg)'" in page
    assert "color: 'var(--error-text)'" in page
    assert "color: 'white'" not in page


def test_monitoring_stage_labels_reflect_component_status():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    assert "{statusText(status)}" in page
    assert "badge: 'Berjalan'" not in page


def test_dashboard_and_monitoring_only_timestamp_complete_refreshes():
    dashboard = (ROOT / "frontend/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
    monitoring = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    freshness = (ROOT / "frontend/src/DataFreshness.jsx").read_text(encoding="utf-8")
    assert "dashboardResult.status === 'fulfilled' && queueResult.status === 'fulfilled'" in dashboard
    assert "statsRes.status === 'fulfilled' && healthRes.status === 'fulfilled' && queueRes.status === 'fulfilled'" in monitoring
    assert "partial" in dashboard
    assert "partial" in monitoring
    assert "partial" in freshness


def test_claims_list_uses_real_link_instead_of_clickable_table_row():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "<Link" in page
    assert "className=\"claim-link\"" in page
    assert "role=\"button\"" not in page
    assert "tabIndex=\"0\"" not in page


def test_queue_timing_is_explicitly_labeled_as_capped_sample():
    page = (ROOT / "frontend/src/QueueSummary.jsx").read_text(encoding="utf-8")
    summary = (ROOT / "frontend/src/queueSummaryData.js").read_text(encoding="utf-8")
    assert "Rata-rata waktu pemeriksaan" in page
    assert "Rata-rata waktu verifikasi" in page
    assert "1.000" in page
    assert "Sampel:" in page
    assert "limit: 1000" in summary


def test_monitoring_renders_queue_worker_health_component():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    api = (ROOT / "backend/app/api/main.py").read_text(encoding="utf-8")
    assert "queue_worker" in page
    assert "queue_worker" in api


def test_health_contract_degrades_when_any_component_is_not_ok():
    api = (ROOT / "backend/app/api/main.py").read_text(encoding="utf-8")
    assert "overall_health_status" in api
    assert "overall = overall_health_status(components)" in api


def test_monitoring_maps_degraded_health_to_attention_state():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    assert "degraded" in page
    assert "Perlu perhatian" in page
    assert "var(--warning-text)" in page


def test_investigation_offers_retry_for_failed_claims():
    page = (ROOT / "frontend/src/pages/Investigation.jsx").read_text(encoding="utf-8")
    assert "retry: true" in page
    assert "Ulangi Pemeriksaan" in page


def test_assessment_guards_analysis_and_decision_effects_by_claim_generation():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert "analysisGenerationRef" in page
    assert "decisionGenerationRef" in page
    assert "cancelled" in page


def test_assessment_decision_post_uses_cancellation_and_persisted_timestamp():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert "decisionPostGenerationRef" in page
    assert "AbortController" in page
    assert "verified_at" in page
    assert "timestamp: new Date().toISOString()" not in page


def test_assessment_renders_stale_analysis_state_explicitly():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert "existing.status === 'stale'" in page
    assert "Hasil pemeriksaan tersimpan dibuat dengan" in page


def test_assessment_similarity_details_are_keyboard_accessible():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert 'type="button"' in page
    assert "aria-expanded={expandedSimilar === sc.claim_id}" in page
    assert "aria-controls={`similar-claim-${sc.claim_id}`}" in page
    assert page.count('scope="col"') >= 4
    assert not re.search(r"<tr\s+\n?\s*onClick=.*expandedSimilar", page)


def test_claims_list_initializes_priority_from_url_query():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "useSearchParams" in page
    assert "searchParams.get('tier')" in page


def test_app_moves_focus_to_main_when_the_route_changes():
    app = (ROOT / "frontend/src/App.jsx").read_text(encoding="utf-8")
    assert "useLocation" in app
    assert "useRef" in app
    assert "mainRef.current?.focus()" in app
    assert "[location.pathname]" in app
    assert "[location.pathname, location.search]" not in app


def test_assessment_qa_summary_preserves_visible_keyboard_focus():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert "outline: 'none'" not in page


def test_assessment_similarity_toggle_meets_touch_target_size():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert 'className="similar-claim-toggle"' in page
    assert ".similar-claim-toggle" in css
    assert "min-height: 44px" in css
    assert "padding: 0.5rem 0.75rem" in css


def test_claims_list_writes_priority_changes_to_router_search_params():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "setSearchParams" in page
    assert "updateFilter('tier', e.target.value)" in page
    assert "nextParams.set(name, value)" in page
    assert "nextParams.delete(name)" in page


def test_claims_list_syncs_date_filters_to_router_search_params():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "received_from" in page
    assert "received_to" in page
    assert "admission_from" in page
    assert "admission_to" in page
    assert "FILTER_PARAMS" in page


def test_touch_targets_are_at_least_44px_without_a_fixed_32px_override():
    assessment = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    claims = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert 'className="assessment-qa-summary"' in assessment
    assert "claims-filter-control" in claims
    assert ".assessment-qa-summary" in css
    assert ".claims-filter-control" in css
    assert ".data-freshness .btn" in css
    assert "min-height: 44px" in css
    assert "min-height: 32px" not in css


def test_shared_interactive_controls_keep_44px_hit_height_without_all_transitions():
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert re.search(r"\.btn\s*\{[^}]*min-height: 44px", css, re.DOTALL)
    assert re.search(r"\.form-input, \.form-select, \.form-textarea\s*\{[^}]*min-height: 44px", css, re.DOTALL)
    assert re.search(r"\.nav-item\s*\{[^}]*min-height: 44px", css, re.DOTALL)
    assert re.search(r"\.sidebar-nav \.nav-item\s*\{[^}]*min-height: 44px", css, re.DOTALL)
    assert re.search(r"\.claim-link\s*\{[^}]*min-height: 44px", css, re.DOTALL)
    assert "transition: all" not in css


def test_monitoring_distinguishes_failed_analytics_from_zero_metrics():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    assert "analyticsError" in page
    assert "statsRes.status === 'fulfilled'" in page
    assert "setAnalyticsError(true)" in page
    assert "Data analitik gagal dimuat" in page
    assert "Coba lagi" in page
    assert "value == null ? '—'" in page


def test_monitoring_keeps_health_data_and_announces_recovery_failures():
    page = (ROOT / "frontend/src/pages/Monitoring.jsx").read_text(encoding="utf-8")
    assert "healthError" in page
    assert "setHealthError(true)" in page
    assert "setHealth({ status: 'error', components: {} })" not in page
    assert 'className="monitoring-health-state" role="alert"' in page
    assert 'className="monitoring-live-status" role="status" aria-live="polite"' in page
    assert 'monitoring-analytics-state" role="alert"' in page


def test_assessment_decision_options_and_progress_bar_avoid_small_or_width_motion_targets():
    assessment = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/index.css").read_text(encoding="utf-8")
    assert 'className="assessment-decision-option"' in assessment
    assert re.search(r"\.assessment-decision-option\s*\{[^}]*min-height: 44px", css, re.DOTALL)
    assert "transition: width" not in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_investigation_announces_only_the_latest_timeline_update():
    page = (ROOT / "frontend/src/pages/Investigation.jsx").read_text(encoding="utf-8")
    assert 'className="investigation-live-status" role="status" aria-live="polite" aria-atomic="true"' in page
    assert "logs[logs.length - 1]" in page


def test_investigation_checks_reduced_motion_before_smooth_scrolling():
    page = (ROOT / "frontend/src/pages/Investigation.jsx").read_text(encoding="utf-8")
    assert "matchMedia('(prefers-reduced-motion: reduce)')" in page
    assert "behavior: prefersReducedMotion ? 'auto' : 'smooth'" in page


def test_claims_list_has_a_preexisting_polite_status_region_for_refreshes():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert 'className="claims-list-live-status" role="status" aria-live="polite" aria-atomic="true"' in page
    assert "Memperbarui daftar klaim..." in page
    assert "data.total" in page


def test_processed_claims_explain_that_human_verification_is_pending():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "Menunggu keputusan petugas" in page


def test_assessment_decision_radios_have_fieldset_legend_semantics():
    page = (ROOT / "frontend/src/pages/Assessment.jsx").read_text(encoding="utf-8")
    assert '<fieldset className="assessment-decision-fieldset">' in page
    assert '<legend className="sr-only">Keputusan Petugas Verifier</legend>' in page


def test_claims_and_data_freshness_keep_polite_refresh_announcements_persistent():
    claims = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    freshness = (ROOT / "frontend/src/DataFreshness.jsx").read_text(encoding="utf-8")
    assert "refreshing" in claims
    assert "Memperbarui daftar klaim..." in claims
    assert 'className="claims-list-live-status" role="status" aria-live="polite" aria-atomic="true"' in claims
    assert 'role="status" aria-live="polite" aria-atomic="true"' in freshness
    assert "refreshing ? `${label} sedang diperbarui.`" in freshness
    assert "error ? `${label} belum berhasil diperbarui.`" in freshness
    assert "role={stale ? 'status' : undefined}" not in freshness


def test_decisions_require_locked_current_lifecycle_and_analysis_queries():
    claims = (ROOT / "backend/app/api/claims.py").read_text(encoding="utf-8")
    assert 'claim_rec.status not in ["processed", "review_required", "verified"]' in claims
    assert "RiskAnalysisRecord.analysis_version == ANALYSIS_VERSION" in claims
    assert re.search(r"select\(ClaimRecord\).*ClaimRecord.claim_id == claim_id.*with_for_update", claims, re.DOTALL)
    assert "HumanDecisionRecord.analysis_generation" in claims
    assert "analysis_generation=claim_rec.analysis_generation" in claims


def test_refreshing_pages_cancel_and_ignore_older_requests():
    for filename in ("ClaimsList.jsx", "Dashboard.jsx", "Monitoring.jsx"):
        page = (ROOT / "frontend/src/pages" / filename).read_text(encoding="utf-8")
        assert "new AbortController()" in page, filename
        assert "requestGenerationRef" in page, filename
        assert "signal: controller.signal" in page, filename
        assert "generation !== requestGenerationRef.current" in page, filename


def test_claims_initial_error_passes_partial_state_to_data_freshness():
    page = (ROOT / "frontend/src/pages/ClaimsList.jsx").read_text(encoding="utf-8")
    assert "partial={Boolean(error)}" in page
    assert "errorMessage={error}" in page
    assert "onRefresh={fetchClaims}" in page


def test_dashboard_lifecycle_chart_uses_exclusive_status_fields():
    page = (ROOT / "frontend/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
    for field in (
        "pending_claims",
        "scanning_claims",
        "review_required_claims",
        "processed_status_claims",
        "verified_claims",
        "failed_claims",
    ):
        assert f"stats?.{field}" in page
