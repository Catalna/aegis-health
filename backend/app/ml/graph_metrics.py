"""
Precomputed provider network metrics (pengganti live graph query).

Sesuai PRD Section 9: static graph view dihitung batch — bukan live query.
Metrik per provider (dari seluruh klaim di DB):
  - claim_count          : volume klaim provider
  - distinct_patients    : jumlah pasien unik
  - patients_per_claim   : rasio pasien/klaim (rendah = banyak klaim utk pasien sama)
  - cost_vs_peer         : rata-rata (cost / peer_baseline) provider
  - anomaly_score 0-1    : komposit ternormalisasi dari penyimpangan metrik di atas

Dihitung sekali di startup + di-refresh setelah demo generation / intake baru,
lalu di-cache di memori untuk dipakai Fraud Agent (tanpa query per-klaim).
"""
from __future__ import annotations

import asyncio
from backend.app.models.database import AsyncSessionLocal, ClaimRecord
from backend.app.ml.feature_engineering import PEER_BASELINE
from sqlalchemy.future import select

_cache: dict[str, dict] = {}
_global_stats: dict = {}


async def refresh_graph_metrics() -> dict:
    """Hitung ulang metrik jaringan provider dari seluruh klaim di DB."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ClaimRecord))
        claims = result.scalars().all()

    providers: dict[str, list] = {}
    for c in claims:
        providers.setdefault(c.provider_id, []).append(c)

    # Statistik global rasio cost/peer untuk normalisasi
    ratios_all: list[float] = []
    provider_rows: dict[str, dict] = {}
    for pid, plist in providers.items():
        ratios = []
        for c in plist:
            base = c.diagnosis_primary.split(".")[0]
            peer = PEER_BASELINE.get(base)
            if peer:
                ratios.append(c.cost_claimed / peer)
        mean_ratio = (sum(ratios) / len(ratios)) if ratios else 1.0
        patients_per_claim = len({p.patient_id for p in plist}) / len(plist)
        provider_rows[pid] = {
            "claim_count": len(plist),
            "distinct_patients": len({p.patient_id for p in plist}),
            "patients_per_claim": round(patients_per_claim, 3),
            "mean_cost_vs_peer": round(mean_ratio, 3),
        }
        ratios_all.extend(ratios)

    if ratios_all:
        import statistics
        g_mean = statistics.fmean(ratios_all)
        g_std = statistics.pstdev(ratios_all) or 1.0
    else:
        g_mean, g_std = 1.0, 1.0

    _global_stats = {"mean_cost_vs_peer": round(g_mean, 4), "std_cost_vs_peer": round(g_std, 4)}

    for pid, row in provider_rows.items():
        # z-score biaya provider terhadap populasi provider
        z_cost = (row["mean_cost_vs_peer"] - g_mean) / g_std
        # Volume tidak wajar: provider dengan banyak klaim + pasien sedikit (repeat pattern)
        volume_flag = max(0.0, 1.5 - row["patients_per_claim"])  # 1.5 = baseline sehat
        cost_flag = max(0.0, min(z_cost / 3.0, 1.0))             # z>=3 → maksimum
        volume_flag = min(volume_flag / 1.5, 1.0)
        anomaly = round(min(1.0, 0.6 * cost_flag + 0.4 * volume_flag), 3)
        row["anomaly_score"] = anomaly
        _cache[pid] = row

    return {"providers": len(_cache), "claims": len(claims)}


def get_provider_metrics(provider_id: str) -> dict:
    """Ambil metrik cached untuk satu provider (default netral jika belum ada data)."""
    return _cache.get(provider_id, {
        "claim_count": 0,
        "distinct_patients": 0,
        "patients_per_claim": 1.0,
        "mean_cost_vs_peer": 1.0,
        "anomaly_score": 0.0,
    })


def graph_stats() -> dict:
    return {"providers_cached": len(_cache), **_global_stats}


def refresh_sync_safe() -> None:
    """Wrapper fire-and-forget untuk dipanggil dari endpoint async."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(refresh_graph_metrics())
    except RuntimeError:
        pass
