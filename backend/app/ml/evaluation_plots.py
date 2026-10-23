"""Threshold metrics and deterministic SVG charts for synthetic v2 evaluation.

No plotting dependency is required: charts are emitted as deterministic SVG.
All figures are for synthetic demonstrator data, never for BPJS validation.
"""

from __future__ import annotations

import html
import math
from typing import Any, Iterable, Sequence

import numpy as np

# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
INK = "#0f172a"
MUTED = "#64748b"
SUBTLE = "#94a3b8"
GRID = "#e5e7eb"
AXIS = "#cbd5e1"
PANEL = "#f8fafc"
ACCENT = "#0f766e"
ACCENT_SOFT = "#99f6e4"
RED = "#b91c1c"
BLUE = "#1d4ed8"
AMBER = "#b45309"
VIOLET = "#6d28d9"
GRAY = "#64748b"
GREEN = "#15803d"


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _as_arrays(labels, scores) -> tuple[np.ndarray, np.ndarray]:
    labels = np.asarray(labels, dtype=np.int32).ravel()
    scores = np.asarray(scores, dtype=np.float64).ravel()
    if len(labels) != len(scores):
        raise ValueError("labels and scores must have equal lengths")
    return labels, scores


def threshold_metrics(labels, scores, threshold: float) -> dict[str, Any]:
    """Binary metrics at a fixed threshold. Positive means score >= threshold."""
    labels, scores = _as_arrays(labels, scores)
    predicted = scores >= float(threshold)
    positive = labels == 1
    tp = int(np.sum(predicted & positive))
    fp = int(np.sum(predicted & ~positive))
    tn = int(np.sum(~predicted & ~positive))
    fn = int(np.sum(~predicted & positive))
    n = int(len(labels))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    accuracy = (tp + tn) / n if n else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    balanced = (recall + specificity) / 2
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = (tp * tn - fp * fn) / denominator if denominator else 0.0
    return {
        "threshold": float(threshold),
        "n": n,
        "predicted_positive_n": tp + fp,
        "alert_rate": (tp + fp) / n if n else 0.0,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": balanced,
        "mcc": mcc,
        "false_positive_rate": 1.0 - specificity,
        "false_negative_rate": 1.0 - recall,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
    }


def _curve_counts(labels: np.ndarray, scores: np.ndarray):
    order = np.argsort(-scores, kind="mergesort")
    ordered_scores = scores[order]
    ordered_labels = labels[order]
    last = np.r_[np.flatnonzero(np.diff(ordered_scores) != 0), len(ordered_scores) - 1]
    true_positive = np.cumsum(ordered_labels)[last]
    false_positive = np.cumsum(1 - ordered_labels)[last]
    return true_positive, false_positive, ordered_scores[last]


def select_threshold(labels, scores) -> dict[str, Any]:
    """Pick the F1-maximising threshold on validation scores only.

    Ties resolve to the highest threshold (deterministic, fewer alerts).
    """
    labels, scores = _as_arrays(labels, scores)
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return {
            "status": "not_computable",
            "reason": "threshold selection needs both classes",
            "threshold": 0.5,
            "selection_rule": "fallback_default",
        }
    tp, fp, thresholds = _curve_counts(labels, scores)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / positives
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros_like(precision), where=(precision + recall) > 0)
    best = int(np.argmax(f1))
    return {
        "status": "measured",
        "threshold": float(thresholds[best]),
        "selection_rule": "max_f1_on_validation",
        "validation_f1": float(f1[best]),
        "validation_precision": float(precision[best]),
        "validation_recall": float(recall[best]),
        "candidate_thresholds": int(len(thresholds)),
    }


def threshold_sweep(labels, scores, points: int = 101) -> dict[str, Any]:
    """Metrics across a fixed grid, for plotting only (no selection)."""
    labels, scores = _as_arrays(labels, scores)
    if len(scores) == 0:
        return {"thresholds": [], "precision": [], "recall": [], "f1": []}
    grid = np.linspace(float(scores.min()), float(scores.max()), max(2, points))
    precision, recall, f1 = [], [], []
    for threshold in grid:
        item = threshold_metrics(labels, scores, float(threshold))
        precision.append(item["precision"])
        recall.append(item["recall"])
        f1.append(item["f1"])
    return {
        "thresholds": grid.tolist(),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def roc_auc(labels, scores) -> float | None:
    labels, scores = _as_arrays(labels, scores)
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=np.float64)
    index = 0
    while index < len(sorted_scores):
        end = index + 1
        while end < len(sorted_scores) and sorted_scores[end] == sorted_scores[index]:
            end += 1
        ranks[order[index:end]] = (index + 1 + end) / 2.0
        index = end
    rank_sum = float(ranks[labels == 1].sum())
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def roc_curve(labels, scores, max_points: int = 600) -> dict[str, Any]:
    labels, scores = _as_arrays(labels, scores)
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return {"fpr": [], "tpr": [], "auc": None}
    tp, fp, _ = _curve_counts(labels, scores)
    tpr = np.r_[0.0, tp / positives]
    fpr = np.r_[0.0, fp / negatives]
    if len(fpr) > max_points:
        keep = np.unique(np.linspace(0, len(fpr) - 1, max_points).astype(int))
        fpr, tpr = fpr[keep], tpr[keep]
    return {"fpr": fpr.tolist(), "tpr": tpr.tolist(), "auc": roc_auc(labels, scores)}


def average_precision(labels, scores) -> float | None:
    labels, scores = _as_arrays(labels, scores)
    positives = int(labels.sum())
    if positives == 0:
        return None
    order = np.argsort(-scores, kind="mergesort")
    ranked = labels[order]
    hits = 0
    total = 0.0
    for index, label in enumerate(ranked, start=1):
        if label:
            hits += 1
            total += hits / index
    return total / positives


def precision_recall_curve(labels, scores, max_points: int = 600) -> dict[str, Any]:
    labels, scores = _as_arrays(labels, scores)
    positives = int(labels.sum())
    if positives == 0:
        return {"recall": [], "precision": [], "ap": None}
    tp, fp, _ = _curve_counts(labels, scores)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / positives
    precision = np.r_[1.0, precision]
    recall = np.r_[0.0, recall]
    if len(recall) > max_points:
        keep = np.unique(np.linspace(0, len(recall) - 1, max_points).astype(int))
        precision, recall = precision[keep], recall[keep]
    return {"recall": recall.tolist(), "precision": precision.tolist(), "ap": average_precision(labels, scores)}


def probability_scores(labels, scores) -> dict[str, Any]:
    """Brier, log loss and ECE for probabilistic candidate scores."""
    labels, scores = _as_arrays(labels, scores)
    clipped = np.clip(scores, 1e-12, 1 - 1e-12)
    positive = labels == 1
    brier = float(np.mean((clipped - labels) ** 2))
    log_loss = float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped)))
    bins = []
    ece = 0.0
    for index in range(15):
        low, high = index / 15, (index + 1) / 15
        mask = (clipped >= low) & (clipped < high if index < 14 else clipped <= high)
        count = int(mask.sum())
        if not count:
            continue
        confidence = float(clipped[mask].mean())
        observed = float(positive[mask].mean())
        ece += count / len(clipped) * abs(observed - confidence)
        bins.append({
            "low": low,
            "high": high,
            "count": count,
            "mean_score": confidence,
            "observed_rate": observed,
        })
    return {
        "brier_score": brier,
        "log_loss": log_loss,
        "expected_calibration_error": float(ece),
        "calibration_bins": bins,
        "prevalence": float(positive.mean()),
    }


def score_histogram(labels, scores, bins: int = 40) -> dict[str, Any]:
    labels, scores = _as_arrays(labels, scores)
    edges = np.linspace(0.0, 1.0, bins + 1)
    positive = scores[labels == 1]
    negative = scores[labels == 0]
    positive_counts, _ = np.histogram(np.clip(positive, 0, 1), bins=edges)
    negative_counts, _ = np.histogram(np.clip(negative, 0, 1), bins=edges)
    return {
        "edges": edges.tolist(),
        "positive_pct": (positive_counts / max(1, len(positive)) * 100).tolist(),
        "negative_pct": (negative_counts / max(1, len(negative)) * 100).tolist(),
        "positive_n": int(len(positive)),
        "negative_n": int(len(negative)),
    }


# --------------------------------------------------------------------------- #
# SVG primitives
# --------------------------------------------------------------------------- #
WIDTH, HEIGHT = 880, 470
PLOT = (72.0, 108.0, 848.0, 396.0)


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _map(value: float, domain: Sequence[float], target: Sequence[float]) -> float:
    low, high = float(domain[0]), float(domain[1])
    if high == low:
        return (target[0] + target[1]) / 2.0
    ratio = (float(value) - low) / (high - low)
    return target[0] + ratio * (target[1] - target[0])


def _nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    if not math.isfinite(low) or not math.isfinite(high) or high <= low:
        high = low + 1.0
    raw = (high - low) / max(1, count - 1)
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    for multiplier in (1, 2, 2.5, 5, 10):
        step = multiplier * magnitude
        if step >= raw:
            break
    start = math.floor(low / step) * step
    ticks: list[float] = []
    value = start
    while value <= high + step * 1e-6:
        ticks.append(round(value, 10))
        value += step
    return ticks


def _short_number(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}"


def _pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:,.{decimals}f}%"


def _rupiah(value: float) -> str:
    if abs(value) >= 1e9:
        return f"Rp{value / 1e9:,.1f} M"
    if abs(value) >= 1e6:
        return f"Rp{value / 1e6:,.1f} jt"
    if abs(value) >= 1e3:
        return f"Rp{value / 1e3:,.0f} rb"
    return f"Rp{value:,.0f}"


class Canvas:
    def __init__(self, width: int = WIDTH, height: int = HEIGHT):
        self.width = width
        self.height = height
        self.parts: list[str] = []
        self.defs: list[str] = []

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def text(self, x, y, value, size=12, fill=INK, anchor="start", weight="400", opacity=1.0):
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}" opacity="{opacity}">{_esc(value)}</text>'
        )

    def line(self, x1, y1, x2, y2, stroke=AXIS, width=1.0, dash=None, opacity=1.0):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{dash_attr}/>'
        )

    def rect(self, x, y, width, height, fill, stroke="none", rx=0, opacity=1.0):
        self.add(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(0.0, width):.1f}" height="{max(0.0, height):.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" opacity="{opacity}"/>'
        )

    def polyline(self, points, stroke, width=2.0, dash=None, opacity=1.0, fill="none"):
        if len(points) < 2:
            return
        encoded = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<polyline points="{encoded}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" '
            f'opacity="{opacity}"{dash_attr}/>'
        )

    def polygon(self, points, fill, opacity=1.0):
        if len(points) < 3:
            return
        encoded = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        self.add(f'<polygon points="{encoded}" fill="{fill}" opacity="{opacity}"/>')

    def circle(self, x, y, radius, fill, opacity=1.0, stroke="none", stroke_width=1.0):
        self.add(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity}"/>'
        )

    def render(self, aria_label: str) -> str:
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" role="img" aria-label="{_esc(aria_label)}" '
            f'font-family="Segoe UI, Inter, system-ui, -apple-system, Arial, sans-serif">'
            f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>'
            f"{defs}{''.join(self.parts)}</svg>"
        )


def _header(chart: Canvas, title: str, subtitle: str) -> None:
    chart.text(28, 34, title, size=19, weight="600")
    chart.text(28, 56, subtitle, size=12, fill=MUTED)


def _legend(
    chart: Canvas,
    items: Iterable[tuple[str, str, str | None]],
    x: float = 72.0,
    y: float = 80.0,
    max_width: float = 780.0,
) -> None:
    cursor = x
    row = y
    for label, color, dash in items:
        item_width = 30 + 6.6 * len(label)
        if cursor > x and cursor + item_width > x + max_width:
            cursor = x
            row += 20
        chart.line(cursor, row - 4, cursor + 18, row - 4, stroke=color, width=3, dash=dash)
        chart.text(cursor + 24, row, label, size=11, fill=MUTED)
        cursor += item_width


def _axes(
    chart: Canvas,
    area: tuple[float, float, float, float],
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
    x_ticks: Sequence[float],
    y_ticks: Sequence[float],
    x_format,
    y_format,
    x_label: str,
    y_label: str,
    x_grid: bool = False,
) -> None:
    left, top, right, bottom = area
    for tick in y_ticks:
        y = _map(tick, y_domain, (bottom, top))
        chart.line(left, y, right, y, stroke=GRID, width=1)
        chart.text(left - 10, y + 4, y_format(tick), size=11, fill=MUTED, anchor="end")
    for tick in x_ticks:
        x = _map(tick, x_domain, (left, right))
        if x_grid:
            chart.line(x, top, x, bottom, stroke=GRID, width=1)
        chart.line(x, bottom, x, bottom + 4, stroke=AXIS)
        chart.text(x, bottom + 20, x_format(tick), size=11, fill=MUTED, anchor="middle")
    chart.line(left, top, left, bottom, stroke=AXIS)
    chart.line(left, bottom, right, bottom, stroke=AXIS)
    chart.text((left + right) / 2, bottom + 46, x_label, size=12, fill=MUTED, anchor="middle")
    chart.add(
        f'<text x="{left - 48:.1f}" y="{(top + bottom) / 2:.1f}" font-size="12" fill="{MUTED}" '
        f'text-anchor="middle" transform="rotate(-90 {left - 48:.1f} {(top + bottom) / 2:.1f})">{_esc(y_label)}</text>'
    )


def _unit_axes(chart: Canvas, area, x_label: str, y_label: str) -> None:
    _axes(
        chart, area, (0.0, 1.0), (0.0, 1.0),
        [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        lambda value: f"{value:.1f}", lambda value: f"{value:.1f}",
        x_label, y_label,
    )


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def score_distribution_chart(labels, scores, threshold: float | None = None) -> str:
    data = score_histogram(labels, scores)
    chart = Canvas()
    _header(
        chart,
        "Distribusi skor model",
        "Persentase klaim per kelompok pada natural test; skor kandidat 0–1 (bukan skor risiko runtime).",
    )
    area = PLOT
    left, top, right, bottom = area
    peak = max(max(data["positive_pct"]), max(data["negative_pct"]))
    y_max = max(1.0, math.ceil(peak / 5.0) * 5.0)
    x_domain, y_domain = (0.0, 1.0), (0.0, y_max)
    y_ticks = _nice_ticks(0, y_max, 6)
    _axes(
        chart, area, x_domain, y_domain,
        [0, 0.2, 0.4, 0.6, 0.8, 1.0], y_ticks,
        lambda value: f"{value:.1f}", lambda value: f"{value:.0f}%",
        "Skor model kandidat", "Proporsi klaim",
    )
    width = right - left
    bin_width = width / (len(data["edges"]) - 1)
    bar_width = bin_width * 0.40
    for index, value in enumerate(data["negative_pct"]):
        x = left + index * bin_width + bin_width * 0.06
        height = _map(value, y_domain, (bottom, top)) - bottom
        chart.rect(x, _map(value, y_domain, (bottom, top)), bar_width, bottom - _map(value, y_domain, (bottom, top)), "#94a3b8", opacity=0.55)
    for index, value in enumerate(data["positive_pct"]):
        x = left + index * bin_width + bin_width * 0.52
        chart.rect(x, _map(value, y_domain, (bottom, top)), bar_width, bottom - _map(value, y_domain, (bottom, top)), RED, opacity=0.78)
    if threshold is not None:
        x = _map(threshold, x_domain, (left, right))
        chart.line(x, top, x, bottom, stroke=ACCENT, width=2, dash="6 4")
        chart.text(min(x + 8, right - 130), top + 16, f"Ambang {threshold:.4f}", size=11, fill=ACCENT, weight="600")
    _legend(chart, [("Normal", "#94a3b8", None), ("Anomali", RED, None)], x=left, y=90)
    return chart.render("Distribusi skor model pada klaim normal dan anomali")


def pr_curve_chart(curves: list[dict[str, Any]]) -> str:
    chart = Canvas()
    _header(
        chart,
        "Kurva Precision–Recall",
        "Natural test; makin dekat ke sudut kanan atas makin baik. Baseline memakai skor yang berbeda skala.",
    )
    area = PLOT
    _unit_axes(chart, area, "Recall", "Precision")
    for curve in curves:
        points = [
            (_map(recall, (0, 1), (area[0], area[2])), _map(precision, (0, 1), (area[3], area[1])))
            for recall, precision in zip(curve["recall"], curve["precision"])
        ]
        chart.polyline(points, stroke=curve["color"], width=2.4 if curve.get("primary") else 1.7, dash=curve.get("dash"))
    items = []
    for curve in curves:
        items.append((curve["label"], curve["color"], curve.get("dash")))
    _legend(chart, items, x=area[0], y=90)
    return chart.render("Kurva precision-recall")


def roc_curve_chart(fpr, tpr, auc: float | None) -> str:
    chart = Canvas()
    _header(
        chart,
        "Kurva ROC",
        "Natural test. ROC-AUC mengukur peringkat bebas ambang; garis diagonal = acak.",
    )
    area = PLOT
    _unit_axes(chart, area, "False positive rate", "True positive rate")
    chart.line(area[0], area[3], area[2], area[1], stroke=SUBTLE, width=1.5, dash="5 5")
    points = [
        (_map(x, (0, 1), (area[0], area[2])), _map(y, (0, 1), (area[3], area[1])))
        for x, y in zip(fpr, tpr)
    ]
    chart.polyline(points, stroke=ACCENT, width=2.6)
    label = f"Model kandidat (AUC {auc:.4f})" if auc is not None else "Model kandidat"
    _legend(chart, [(label, ACCENT, None), ("Acak (AUC 0.500)", SUBTLE, "5 5")], x=area[0], y=90)
    return chart.render("Kurva ROC model kandidat")


def threshold_sweep_chart(sweep: dict[str, Any], selected: float | None) -> str:
    chart = Canvas()
    _header(
        chart,
        "Sapuan ambang keputusan",
        "Dihitung pada validation. Ambang terpilih (F1 maksimum) dibekukan sebelum evaluasi test.",
    )
    area = PLOT
    left, top, right, bottom = area
    thresholds = sweep["thresholds"]
    if not thresholds:
        return chart.render("Sapuan ambang tidak tersedia")
    x_domain = (float(min(thresholds)), float(max(thresholds)))
    y_domain = (0.0, 1.0)
    x_ticks = _nice_ticks(x_domain[0], x_domain[1], 6)
    _axes(
        chart, area, x_domain, y_domain, x_ticks,
        [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        lambda value: f"{value:.2f}", lambda value: f"{value:.1f}",
        "Ambang skor", "Nilai metrik",
    )
    for key, color, label in (("precision", BLUE, "Precision"), ("recall", AMBER, "Recall"), ("f1", ACCENT, "F1")):
        points = [
            (_map(x, x_domain, (left, right)), _map(y, y_domain, (bottom, top)))
            for x, y in zip(thresholds, sweep[key])
        ]
        chart.polyline(points, stroke=color, width=2.2 if key == "f1" else 1.7)
    if selected is not None:
        x = _map(selected, x_domain, (left, right))
        chart.line(x, top, x, bottom, stroke=RED, width=1.6, dash="6 4")
        chart.text(min(x + 8, right - 150), top + 16, f"Terpilih {selected:.4f}", size=11, fill=RED, weight="600")
    _legend(chart, [("Precision", BLUE, None), ("Recall", AMBER, None), ("F1", ACCENT, None)], x=left, y=90)
    return chart.render("Sapuan ambang precision, recall, dan F1")


def confusion_matrix_chart(metrics: dict[str, Any]) -> str:
    chart = Canvas()
    _header(
        chart,
        "Confusion matrix pada ambang terpilih",
        f"Natural test, ambang {metrics['threshold']:.4f} dari validation. Angka = jumlah klaim.",
    )
    area = (250.0, 128.0, 650.0, 360.0)
    left, top, right, bottom = area
    cell_w = (right - left) / 2
    cell_h = (bottom - top) / 2
    values = [
        (metrics["true_negative"], "True negative", "#e2e8f0", INK),
        (metrics["false_positive"], "False positive", "#fecaca", "#7f1d1d"),
        (metrics["false_negative"], "False negative", "#fde68a", "#78350f"),
        (metrics["true_positive"], "True positive", "#99f6e4", "#134e4a"),
    ]
    positions = [(left, top), (left + cell_w, top), (left, top + cell_h), (left + cell_w, top + cell_h)]
    for (count, label, fill, color), (x, y) in zip(values, positions):
        chart.rect(x + 3, y + 3, cell_w - 6, cell_h - 6, fill, rx=8)
        chart.text(x + cell_w / 2, y + cell_h / 2 - 4, f"{count:,}", size=28, fill=color, anchor="middle", weight="700")
        chart.text(x + cell_w / 2, y + cell_h / 2 + 20, label, size=12, fill=color, anchor="middle")
    chart.text((left + right) / 2, top - 22, "Prediksi", size=12, fill=MUTED, anchor="middle", weight="600")
    chart.add(
        f'<text x="{left - 48:.1f}" y="{(top + bottom) / 2:.1f}" font-size="12" fill="{MUTED}" '
        f'text-anchor="middle" font-weight="600" transform="rotate(-90 {left - 48:.1f} {(top + bottom) / 2:.1f})">Label aktual</text>'
    )
    chart.text(left + cell_w / 2, top - 2, "Normal", size=11, fill=MUTED, anchor="middle")
    chart.text(left + cell_w * 1.5, top - 2, "Anomali", size=11, fill=MUTED, anchor="middle")
    chart.text(left - 12, top + cell_h / 2 + 4, "Normal", size=11, fill=MUTED, anchor="end")
    chart.text(left - 12, top + cell_h * 1.5 + 4, "Anomali", size=11, fill=MUTED, anchor="end")
    summary = (
        f"Accuracy {_pct(metrics['accuracy'])}  ·  Precision {_pct(metrics['precision'])}  ·  "
        f"Recall {_pct(metrics['recall'])}  ·  F1 {_pct(metrics['f1'])}"
    )
    chart.text((left + right) / 2, bottom + 34, summary, size=12, fill=MUTED, anchor="middle")
    return chart.render("Confusion matrix pada ambang terpilih")


def metric_bar_chart(items: list[tuple[str, float]]) -> str:
    chart = Canvas(height=150 + 34 * max(1, len(items)))
    _header(
        chart,
        "Ringkasan metrik klasifikasi",
        "Natural test pada ambang validation. Semua nilai 0–1; makin tinggi makin baik.",
    )
    left, top, right = 250.0, 112.0, 812.0
    row_height = 34.0
    label_width = right - left
    for index, (label, value) in enumerate(items):
        y = top + index * row_height
        chart.text(left - 14, y + 13, label, size=12, fill=INK, anchor="end")
        chart.rect(left, y, label_width, 18, "#eef2f7", rx=9)
        fill = ACCENT if value >= 0.5 else AMBER if value >= 0.3 else RED
        chart.rect(left, y, max(2.0, label_width * max(0.0, min(1.0, value))), 18, fill, rx=9)
        chart.text(min(left + label_width * value + 10, right + 6), y + 13, f"{value:.4f}", size=11, fill=MUTED)
    return chart.render("Ringkasan metrik klasifikasi")


def ap_by_type_chart(items: dict[str, dict[str, Any]], title: str, subtitle: str) -> str:
    chart = Canvas(height=130 + 34 * max(1, len(items)))
    _header(chart, title, subtitle)
    left, top, right = 230.0, 104.0, 812.0
    row_height = 34.0
    width = right - left
    for index, (label, metrics) in enumerate(items.items()):
        y = top + index * row_height
        value = metrics.get("average_precision") or 0.0
        chart.text(left - 14, y + 13, label, size=12, fill=INK, anchor="end")
        chart.rect(left, y, width, 18, "#eef2f7", rx=9)
        fill = ACCENT if value >= 0.5 else AMBER if value >= 0.2 else RED
        chart.rect(left, y, max(2.0, width * value), 18, fill, rx=9)
        positives = metrics.get("raw_positive_n")
        suffix = f"  (n+={positives:,})" if positives else ""
        chart.text(min(left + width * value + 10, right - 90), y + 13, f"AP {value:.3f}{suffix}", size=11, fill=MUTED)
    return chart.render(title)


def cost_scatter_chart(actual, predicted, seed: int = 42, sample_size: int = 3500) -> str:
    actual = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(predicted, dtype=np.float64)
    if len(actual) > sample_size:
        rng = np.random.default_rng(seed)
        index = rng.choice(len(actual), size=sample_size, replace=False)
        actual, predicted = actual[index], predicted[index]
    chart = Canvas()
    _header(
        chart,
        "Prediksi vs biaya aktual",
        f"Sampel {len(actual):,} klaim normal pada test. Garis putus-putus = prediksi sempurna.",
    )
    area = (82.0, 108.0, 836.0, 396.0)
    left, top, right, bottom = area
    peak = max(float(actual.max()), float(predicted.max())) * 1.04
    x_domain, y_domain = (0.0, peak), (0.0, peak)
    ticks = _nice_ticks(0, peak / 1e6, 6)
    _axes(
        chart, area, x_domain, y_domain,
        [tick * 1e6 for tick in ticks], [tick * 1e6 for tick in ticks],
        lambda value: f"{value / 1e6:.0f}", lambda value: f"{value / 1e6:.0f}",
        "Biaya aktual (juta Rp)", "Prediksi biaya (juta Rp)",
    )
    chart.line(left, bottom, right, top, stroke=SUBTLE, width=1.4, dash="5 5")
    for x_value, y_value in zip(actual, predicted):
        chart.circle(
            _map(x_value, x_domain, (left, right)),
            _map(y_value, y_domain, (bottom, top)),
            1.6, ACCENT, opacity=0.22,
        )
    return chart.render("Scatter prediksi versus biaya aktual")


def residual_histogram_chart(relative_errors, bins: int = 46) -> str:
    values = np.asarray(relative_errors, dtype=np.float64)
    values = values[np.isfinite(values)]
    clipped = np.clip(values, -0.6, 0.6)
    counts, edges = np.histogram(clipped, bins=bins, range=(-0.6, 0.6))
    percentages = counts / max(1, len(values)) * 100
    chart = Canvas()
    _header(
        chart,
        "Distribusi error relatif regressor",
        f"Natural test, {len(values):,} klaim normal. Error = (prediksi − aktual) / aktual; ekor dipotong di ±60%.",
    )
    area = PLOT
    left, top, right, bottom = area
    y_max = max(1.0, math.ceil(float(percentages.max()) / 2.0) * 2.0)
    _axes(
        chart, area, (-0.6, 0.6), (0.0, y_max),
        [-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6], _nice_ticks(0, y_max, 5),
        lambda value: f"{value * 100:.0f}%", lambda value: f"{value:.0f}%",
        "Error relatif", "Proporsi klaim",
    )
    width = right - left
    bin_width = width / len(percentages)
    for index, value in enumerate(percentages):
        x = left + index * bin_width
        color = ACCENT if edges[index] <= 0 <= edges[index + 1] else BLUE
        chart.rect(x + 0.5, _map(value, (0, y_max), (bottom, top)), max(1.0, bin_width - 1.0),
                   bottom - _map(value, (0, y_max), (bottom, top)), color, opacity=0.8)
    chart.line(_map(0.0, (-0.6, 0.6), (left, right)), top, _map(0.0, (-0.6, 0.6), (left, right)), bottom,
               stroke=RED, width=1.4, dash="4 4")
    median_error = float(np.median(values))
    chart.text(_map(0.0, (-0.6, 0.6), (left, right)) + 8, top + 16, f"Median {median_error * 100:+.1f}%",
               size=11, fill=RED, weight="600")
    return chart.render("Distribusi error relatif regressor biaya")


def coverage_chart(deciles: list[dict[str, Any]], target: float = 0.90) -> str:
    chart = Canvas()
    _header(
        chart,
        "Coverage batas atas per desil prediksi",
        "Target 90%: proporsi klaim aktual yang berada di bawah prediksi + margin. Garis = target.",
    )
    area = PLOT
    left, top, right, bottom = area
    _axes(
        chart, area, (0.0, float(len(deciles))), (0.6, 1.0),
        [index + 0.5 for index in range(len(deciles))],
        [0.6, 0.7, 0.8, 0.9, 1.0],
        lambda value: f"D{int(value) + 1}", lambda value: f"{value * 100:.0f}%",
        "Desil prediksi biaya (D1 terendah)", "Coverage",
    )
    width = right - left
    bar_width = width / max(1, len(deciles)) * 0.62
    for index, item in enumerate(deciles):
        center = left + (index + 0.5) * width / len(deciles)
        top_y = _map(item["coverage"], (0.6, 1.0), (bottom, top))
        chart.rect(center - bar_width / 2, top_y, bar_width, bottom - top_y, ACCENT, opacity=0.72, rx=3)
        chart.text(center, top_y - 6, f"{item['coverage'] * 100:.0f}%", size=10, fill=MUTED, anchor="middle")
    target_y = _map(target, (0.6, 1.0), (bottom, top))
    chart.line(left, target_y, right, target_y, stroke=RED, width=1.6, dash="6 4")
    chart.text(right - 4, target_y - 8, f"Target {target:.0%}", size=11, fill=RED, anchor="end", weight="600")
    return chart.render("Coverage batas atas per desil prediksi")
