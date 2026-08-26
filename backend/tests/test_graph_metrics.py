"""Test Graph Metrics (provider network precomputed) — pengganti proxy palsu."""
import pytest


def test_provider_metrics_default_neutral():
    from backend.app.ml.graph_metrics import get_provider_metrics
    m = get_provider_metrics("FAC-TIDAK-ADA")
    assert m["anomaly_score"] == 0.0
    assert m["patients_per_claim"] == 1.0


def test_graph_stats_shape():
    from backend.app.ml.graph_metrics import graph_stats
    stats = graph_stats()
    assert "providers_cached" in stats
