"""
Similarity engine — LanceDB (embedded) + sentence-transformers.

v3 — KEMIRIPAN KOMPOSIT MULTI-FAKTOR:
Kemiripan profil medis (diagnosis/prosedur/obat) saja TIDAK CUKUP untuk
menyebut dua klaim "mirip secara mencurigakan". Dua klaim penyakit sama dari
faskes berbeda adalah pola wajar. Yang membuat mirip-mencurigakan (cloning/
repeat) adalah kombinasi:

  1. Kode medis   (Jaccard diagnosis+prosedur)          — bobot 40%
  2. Kedekatan biaya (klaim hasil cloning menyalin biaya hampir persis) — 30%
  3. Faskes sama  (cloning terjadi di satu faskes)      — 15%
  4. Jarak waktu  (diklaim berdekatan)                  — 10%
  5. Pasien sama  (indikasi repeat billing)             —  5%

Skor komposit inilah yang ditampilkan sebagai "Kemiripan" — disertai
rincian per-faktor agar verifier melihat MENGAPA dianggap mirip.
Cosine embedding murni hanya dipakai sebagai prefilter kandidat.
"""
import os
import lancedb
from lancedb.pydantic import Vector, LanceModel
from sentence_transformers import SentenceTransformer

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lancedb_data")
os.makedirs(DB_PATH, exist_ok=True)

db = lancedb.connect(DB_PATH)

try:
    model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    print(f"Failed to load SentenceTransformer: {e}")
    model = None

DIM = model.get_sentence_embedding_dimension() if model else 384

# Tabel v3 — skema multi-faktor (admission_date utk faktor waktu)
TABLE_NAME = "claims_vectors_v3"


class ClaimVector(LanceModel):
    claim_id: str
    patient_id: str
    provider_id: str
    doctor_id: str
    diagnosis_primary: str = ""
    cost_claimed: float = 0.0
    admission_date: str = ""  # ISO date, untuk faktor temporal
    vector: Vector(DIM)
    text_content: str


def get_table():
    if TABLE_NAME not in db.table_names():
        return db.create_table(TABLE_NAME, schema=ClaimVector)
    return db.open_table(TABLE_NAME)


def generate_claim_text(claim: dict) -> str:
    """Representasi teks klaim untuk embedding (profil medis saja)."""
    primary = claim.get("diagnosis_primary", "")
    secondary = claim.get("diagnosis_secondary", [])
    if isinstance(secondary, str):
        secondary = [s.strip() for s in secondary.split(",") if s.strip()]
    procs = claim.get("procedure_codes", [])
    if isinstance(procs, str):
        procs = [p.strip() for p in procs.split(",") if p.strip()]
    meds = claim.get("medication", [])
    med_names = [m["name"] if isinstance(m, dict) else m for m in meds]
    return f"Diagnosis: {primary}. Secondary: {', '.join(secondary)}. Procedures: {', '.join(procs)}. Medications: {', '.join(med_names)}."


def _normalize(vec: list[float]) -> list[float]:
    import math
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ---------------------------------------------------------------------------
# Skor komposit
# ---------------------------------------------------------------------------

W_CODE, W_COST, W_PROVIDER, W_TEMPORAL, W_PATIENT = 0.40, 0.30, 0.15, 0.10, 0.05

# Ambang komposit minimum agar dua klaim layak disebut "serupa".
# Kalibrasi:
#   ~0.40-0.49 : hanya kode medis sama + biaya agak dekat, faktor lain beda semua
#                (faskes/pasien/waktu) → pola penyakit wajar, BUKAN "mirip".
#   ~0.55      : kode medis identik + biaya mirip, tanpa faktor konteks.
#   ≥0.60      : butuh kecocokan kode + minimal satu faktor konteks kuat
#                (biaya nyaris sama / faskes sama / waktu dekat) → layak ditampilkan.
SIMILARITY_THRESHOLD = 0.60


def cost_proximity(cost_a: float, cost_b: float) -> float:
    """1.0 = biaya hampir identik; →0 = sangat berbeda."""
    if cost_a <= 0 and cost_b <= 0:
        return 0.0
    hi = max(cost_a, cost_b)
    if hi <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(cost_a - cost_b) / hi)


def temporal_proximity(days_apart: int | None) -> float:
    """1.0 jika ≤7 hari, meluruh ke 0 di 90 hari; None (tanpa tanggal) = 0."""
    if days_apart is None:
        return 0.0
    d = max(0, days_apart)
    if d <= 7:
        return 1.0
    return max(0.0, 1.0 - (d - 7) / 83)


def composite_similarity(
    code_sim: float,
    cost_prox: float,
    same_provider: bool,
    same_patient: bool,
    days_apart: int | None,
) -> float:
    """Skor kemiripan mencurigakan 0-1 dari gabungan faktor (lihat docstring modul)."""
    temporal = temporal_proximity(days_apart)
    return (
        W_CODE * code_sim
        + W_COST * cost_prox
        + W_PROVIDER * (1.0 if same_provider else 0.0)
        + W_TEMPORAL * temporal
        + W_PATIENT * (1.0 if same_patient else 0.0)
    )


def _days_between(date_a: str, date_b: str) -> int | None:
    if not date_a or not date_b:
        return None
    from datetime import date as _date
    try:
        a = _date.fromisoformat(str(date_a)[:10])
        b = _date.fromisoformat(str(date_b)[:10])
        return abs((a - b).days)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Store / search
# ---------------------------------------------------------------------------

def embed_and_store(claims: list[dict]):
    """Embed dan simpan daftar klaim ke LanceDB (idempotent per claim_id)."""
    if not model:
        print("[LanceDB] Model embedding tidak tersedia, lewati.")
        return 0
    table = get_table()
    existing_ids = set()
    try:
        existing_ids = set(table.to_arrow().column("claim_id").to_pylist())
    except Exception:
        pass

    records = []
    for c in claims:
        if c.get("claim_id") in existing_ids:
            continue
        text = generate_claim_text(c)
        emb = _normalize(model.encode(text).tolist())
        procs = c.get("procedure_codes", [])
        if isinstance(procs, str):
            procs = [p.strip() for p in procs.split(",") if p.strip()]
        records.append({
            "claim_id": c["claim_id"],
            "patient_id": c.get("patient_id", ""),
            "provider_id": c.get("provider_id", ""),
            "doctor_id": c.get("doctor_id", ""),
            "diagnosis_primary": c.get("diagnosis_primary", ""),
            "cost_claimed": float(c.get("cost_claimed", 0) or 0),
            "admission_date": str(c.get("admission_date") or ""),
            "vector": emb,
            "text_content": text,
        })
    if records:
        table.add(records)
    return len(records)


def store_single_claim(claim_dict: dict):
    """Index satu klaim (dipanggil setelah intake/demo agar klaim baru bisa dicari)."""
    return embed_and_store([claim_dict])


def _parse_text_content(text: str) -> dict:
    """Parse text_content kembali jadi dict klaim. Pakai section header sebagai
    delimiter (bukan titik) agar kode diagnosis bertitik (mis. S72.0) tidak terpotong."""
    sections = ["Diagnosis", "Secondary", "Procedures", "Medications"]

    def get(name: str) -> str:
        marker = f"{name}: "
        start = text.find(marker)
        if start == -1:
            return ""
        rest = text[start + len(marker):]
        idx = sections.index(name)
        nxt = sections[idx + 1] if idx + 1 < len(sections) else None
        if nxt:
            end = rest.find(f"{nxt}:")
            if end != -1:
                return rest[:end].strip().rstrip(".").strip()
        return rest.strip().rstrip(".").strip()

    split = lambda s: [x.strip() for x in s.split(",") if x.strip()] if s else []
    return {
        "diagnosis_primary": get("Diagnosis"),
        "diagnosis_secondary": split(get("Secondary")),
        "procedure_codes": split(get("Procedures")),
        "medication": [{"name": n.strip(), "quantity": 1} for n in split(get("Medications"))],
    }


def find_similar_claims(claim_id: str, claim_data: dict, limit: int = 5) -> list[dict]:
    """
    Cari klaim historis serupa. Urutan berdasarkan SKOR KOMPOSIT (bukan cosine).
    Cosine embedding hanya prefilter kandidat (profil medis mirip).
    """
    if not model:
        return []

    table = get_table()
    text = generate_claim_text(claim_data)
    emb = _normalize(model.encode(text).tolist())

    # Prefilter: ambil kandidat profil medis terdekat (lebih banyak untuk disaring)
    results = table.search(emb).limit(limit * 4 + 4).to_list()

    claim_cost = float(claim_data.get("cost_claimed", 0) or 0)
    claim_admit = str(claim_data.get("admission_date") or "")
    claim_provider = claim_data.get("provider_id", "")
    claim_patient = claim_data.get("patient_id", "")

    scored = []
    for r in results:
        if r["claim_id"] == claim_id:
            continue

        hist = _parse_text_content(r.get("text_content", ""))
        code_sim = compute_jaccard_similarity(claim_data, hist)

        cand_cost = float(r.get("cost_claimed", 0) or 0)
        c_prox = cost_proximity(claim_cost, cand_cost)

        same_provider = r.get("provider_id", "") == claim_provider and bool(claim_provider)
        same_patient = r.get("patient_id", "") == claim_patient and bool(claim_patient)
        days = _days_between(claim_admit, str(r.get("admission_date") or ""))

        composite = composite_similarity(code_sim, c_prox, same_provider, same_patient, days)

        scored.append({
            "claim_id": r["claim_id"],
            # Skor utama = komposit multi-faktor (0-1)
            "similarity": round(composite, 4),
            # Rincian per faktor — ditampilkan di UI agar transparan
            "code_similarity": round(code_sim, 4),
            "cost_proximity": round(c_prox, 4),
            "same_provider": same_provider,
            "same_patient": same_patient,
            "days_apart": days,
            # Cosine profil medis disimpan sebagai info tambahan
            "profile_cosine": round(max(0.0, min(1.0, 1.0 - (r["_distance"] ** 2) / 2.0)), 4),
            "jaccard": code_sim,
            "provider_id": r.get("provider_id", ""),
            "patient_id": r.get("patient_id", ""),
            "diagnosis_primary": r.get("diagnosis_primary") or hist.get("diagnosis_primary", ""),
            "cost_claimed": cand_cost,
        })

    # Filter ambang: di bawah threshold = pola penyakit wajar, jangan disebut "serupa"
    scored = [s for s in scored if s["similarity"] >= SIMILARITY_THRESHOLD]

    # Urutkan berdasar skor komposit
    scored.sort(key=lambda s: s["similarity"], reverse=True)
    return scored[:limit]


def compute_jaccard_similarity(claim1: dict, claim2: dict) -> float:
    """Kemiripan eksak kode medis (diagnosis + prosedur) antara dua klaim."""
    def codes(c: dict) -> set:
        secondary = c.get("diagnosis_secondary", [])
        if isinstance(secondary, str):
            secondary = [s.strip() for s in secondary.split(",") if s.strip()]
        procs = c.get("procedure_codes", [])
        if isinstance(procs, str):
            procs = [p.strip() for p in procs.split(",") if p.strip()]
        s = {c.get("diagnosis_primary", "")} | set(secondary) | set(procs)
        s.discard("")
        return s

    set1, set2 = codes(claim1), codes(claim2)
    if not set1 and not set2:
        return 0.0
    union = len(set1 | set2)
    return len(set1 & set2) / union if union else 0.0
