# Balanced synthetic dataset design

## Tujuan

Buat varian dataset sintetis calibrated yang memiliki kelas seimbang pada train untuk eksperimen classifier, tanpa mengubah dataset sumber atau prevalensi split evaluasi. Dataset tetap demonstrator sintetis dan bukan validasi performa BPJS.

## Input dan output

- Input sumber: `data/synthetic_v2_calibrated`.
- Output baru: `data/synthetic_v2_calibrated_balanced`.
- Dataset sumber tidak ditimpa.
- Train dibuat dengan generator calibrated dan target rasio `is_anomaly=false:true` sebesar 50:50.
- `validation`, `test`, `test_enriched`, dan `ood` disalin persis dari sumber, termasuk label terpisah.
- Tulis ulang schema/data card agar identitas, konfigurasi, jumlah baris, distribusi label, dan provenance output tercatat.

## Pola label dan hard-negative

Buat laporan profil per `anomaly_type` dan `scenario_family`, termasuk jumlah, prevalensi, tingkat kesulitan, keyakinan label, serta ringkasan fitur numerik/kategorikal yang relevan. Pertahankan keluarga `hard_negative_*` sebagai label normal yang sah; jangan memberi label anomali pada variasi normal. Label tetap berada di file `*_labels`, tidak masuk ke fitur klaim.

## Integritas dan validasi

- Gunakan seed yang eksplisit dan dapat direproduksi.
- Jangan mengubah split evaluasi atau menggunakan data evaluasi untuk membentuk train.
- Pertahankan batas group antar-split dan validasi kontrak generator yang ada.
- Validasi rasio train target, kelengkapan/keunikan ID, keselarasan klaim-label, pemisahan label dari fitur, serta semua split yang dihasilkan sebelum menulis keluaran final.
- Hasil dan dokumentasi menyatakan dengan jelas bahwa train balanced mengubah prior kelas dan metrik utama harus tetap dilaporkan pada validation/test dengan prevalensi natural.

## Di luar cakupan

- Mengganti dataset calibrated sumber.
- Melatih atau mempromosikan model, mengubah runtime scoring, atau mengklaim performa pada data BPJS nyata.
- Mengubah distribusi validation/test demi keseimbangan.
