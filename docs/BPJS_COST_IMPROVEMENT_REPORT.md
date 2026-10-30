# Audit lanjutan kandidat biaya FKRTL (post-grouper, pre-verifikasi)

**Status: offline kandidat; tidak mempromosikan bobot runtime, tidak memvalidasi fraud atau kebutuhan klinis.**
Skrip: `scripts/bpjs/cost_improvement_experiment.py`. Artefak lokal ter-ignasi: `backend/app/data/analysis/cost_improvement/` (dua booster JSON, tabel tarif agregat, kamus fitur, metrik JSON).

## Keputusan desain dan sumber

Sasaran prediksi adalah `FKL48` pada klaim FKRTL yang `FKL47 == FKL48 > 0`. Skenario mengasumsikan kode grup INA-CBG (`FKL19`) dan severitas (`FKL23`) **tersedia dari grouper sebelum verifikasi**. Besarnya tagihan `FKL47` **tidak masuk fitur**. Dataset tidak memberi timestamp verifikasi atau snapshot kode grouper saat awal klaim; sehingga asumsi ketersediaan fitur dan tarif historis **belum terbukti**, juga tidak ada pemeriksaan terhadap salah kode/upcoding.

Split tetap berdasarkan peserta, dengan fit 850.247 dan validasi 283.961 klaim yang **tanggal masuk dan pulangnya** sebelum 1 Nov 2024; test yang pernah dipakai audit sebelumnya berisi 56.385 klaim layanan 1 Nov–31 Des 2024. Peserta ketiga bagian tidak beririsan. Angka test **bukan untouched holdout** karena periode yang sama telah dilihat dalam audit sebelumnya; pemilihan dua konfigurasi di eksperimen ini hanya memakai validasi. Hasil tidak boleh diartikan sebagai jaminan generalisasi eksternal.

Empat level median empiris `FKL48` dari fit: (INACBG, severitas, provinsi, tipe faskes, kelas rawat) → tanpa kelas → tanpa tipe → (INACBG, severitas) → median global. Level rinci memerlukan minimal 20 klaim; level INACBG×severitas memakai minimal satu klaim. Nilai fitur tarif untuk fit dibuat cross-fit 5 fold **per peserta**; validasi/test memakai fit penuh. Ini mencegah klaim peserta sendiri membentuk tarifnya, tetapi tidak membuktikan label sumber median sudah tersedia secara temporal. Kode diagnosis masuk (`FKL15A`) dikodekan memakai kamus fit; kode tidak dikenal = -1. XGBoost memakai kategori INACBG langsung dan fitur konteks dari eksperimen sebelumnya (kelas berarti kelas rawat, bukan kelas RS).

## Seleksi validasi dan evaluasi akhir

Training pada RTX 5050 (XGBoost `device=cuda`, `tree_method=hist`); seed 42, kedalaman 7, hingga 3.000 putaran, 55 round early stopping. Kandidat raw berhenti pada batas **3.000** (belum plateau), kandidat log berhenti pada **2.712** berdasarkan **MAE rupiah** validasi, bukan MAE log. Log-target dikembalikan dengan `expm1` dan keluaran dijaga nonnegatif. Pemenang dipilih oleh MAE validasi, bukan test. Raw XGBoost perlu membatasi 110 output negatif pada validasi; kandidat log tidak menghasilkan output negatif.

Model terpilih dapat dimuat ulang bersama tabel agregat `tariff_level_*.csv` dan `feature_context.json`; replay di GPU menghasilkan **MAE identik** dengan metrik tersimpan. Prediksi CPU dari booster yang sama berbeda sedikit akibat implementasi inferensi numerik: MAE Rp46.275,24 dibanding GPU Rp46.275,96, selisih Rp0,72. Perbedaan angka kecil ini bukan perubahan dataset atau versi bobot.

| Model | Validasi MAPE ↓ | Validasi MAE ↓ | Test MAPE ↓ | Test MAE ↓ | Test RMSE ↓ | Test R² ↑ | Test ≤10% ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Median INACBG×sev | 6,48% | Rp134.030 | 6,56% | Rp137.474 | Rp1.127.772 | 0,8728 | 84,48% |
| Median hierarkis | 2,81% | Rp113.798 | 2,89% | Rp118.557 | Rp1.125.802 | 0,8732 | 91,52% |
| XGBoost raw | 4,57% | Rp50.825 | 4,47% | Rp57.080 | Rp876.737 | 0,9231 | 92,95% |
| **XGBoost log (dipilih)** | **2,07%** | **Rp40.860** | **2,12%** | **Rp46.276** | **Rp654.527** | **0,9572** | **96,82%** |

Pada test yang sama, audit model sebelumnya mencatat MAPE 6,95%, MAE Rp79.735. Perubahan hasil tidak dapat diatribusikan ke satu fitur: desain cohort dan fitur berubah bersama. Ini bukan validasi atas klaim nyata yang ditolak/verifikasi dipotong.

## Tiga risiko dan angka ketidakpastian

1. **As-of tariff / kode grouper:** label tarif berasal dari biaya verifikasi fit, bukan daftar tarif resmi atau snapshot historis. Mengecualikan klaim belum pulang di cutoff (1.103 fit dan 342 validasi dibanding eksperimen terdahulu) menutup satu celah waktu; **tanggal verifikasi** dan riwayat revisi kode tetap tidak tersedia. Jika grouper/kode belum ada saat prediksi, angka di atas tidak berlaku. Bila kode/severitas dimanipulasi, model dapat melegitimasi nilai yang salah karena prediksi bersyarat pada kode itu. Uji terpisah perlu memanipulasi kode sebelum grouper/menilai kecocokan klinis; angka ini bukan sensitivitas upcoding.
2. **Biaya tinggi:** pada `FKL48 > Rp20 juta` terdapat 153 test klaim dari 147 peserta. Pemenang MAPE **8,65%**, MAE **Rp4.763.144**, within ±10% **72,55%**; median sederhana MAPE 26,46%, MAE Rp11.845.888. Paired participant bootstrap 2.000 replikasi (seed 42) memberi selisih MAE XGBoost − median **−Rp7.082.744** dengan CI95 **[−Rp8.381.192, −Rp5.780.020]**. Ini interval pada test terbatas yang *reused*, bukan jaminan masa depan; pemilihan subkelompok berdasarkan biaya aktual hanya untuk analisis, tidak bisa digunakan sebagai aturan skoring sebelum verifikasi.
3. **Diagnosis:** 32 klaim test/16 kode tidak terlihat di fit; n terlalu kecil untuk klaim umum, MAPE 1,19%. Diagnosis langka (frekuensi <100 di fit): 1.748 klaim, MAPE 2,23%, MAE Rp99.286. Diagnosis lain: 54.637 klaim, MAPE 2,12%, MAE Rp44.580. Distribusi biaya berbeda antar-kelompok; audit agregat ini tidak membuktikan bahwa kode langka *menyebabkan* error. Kode diagnosis masuk tidak selalu identik dengan diagnosis akhir E-Klaim.

## Batas tegas dan langkah sebelum promosi

- `FKL19`/`FKL23` adalah informasi pasca-grouper yang belum ada di `ClaimInput` runtime; jangan menukar bobot langsung. Harus ada adapter yang mencatat asal, versi, dan timestamp grouper.
- Tarik **snapshot tarif yang sudah berlaku sebelum tanggal scoring**; bila tanggal verifikasi BPJS tidak ada, jangan menyebut median empiris fit ini "tarif tersedia per 1 Nov". Bandingkan secara terpisah dengan tarif resmi yang sah dan berlisensi apabila dapat diakses.
- Perlu evaluasi *fresh* pada periode rumah sakit/versi tarif lain, seluruh status klaim termasuk koreksi, dan review ahli untuk outlier mahal; tidak boleh menyebut skor ini fraud precision/recall.
- Penyetelan numerik bukan penentu tunggal keberhasilan: klaim dengan kesalahan coding, kelas rawat berbeda, tarif tambahan, dan perubahan regulasi harus dievaluasi sebagai strata khusus. Sampel BPJS ini belum dibobot dengan bobot survei.
- Tabel median nasional fallback untuk sel langka boleh didasarkan satu baris fit; arti klinisnya rendah dan perlu ambang dukungan lebih tinggi sebelum implementasi. Data angka test pernah digunakan dalam investigasi terdahulu; jangan memutar test berkali-kali sebagai dasar seleksi.

**Kesimpulan:** model log-XGBoost adalah kandidat estimasi biaya terbaik **dalam eksperimen terbatas ini**, tidak bisa dipromosikan ke runtime tanpa bukti ketersediaan data pada waktu skoring dan validasi eksternal. Model Isolation Forest tidak disentuh.
