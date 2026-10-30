# Visualisasi Kandidat Biaya BPJS — Log-XGBoost

**Model:** `log_xgb`, kandidat offline post-grouper/pre-verifikasi dengan lookup tarif empiris hierarkis. **Test:** 56.385 klaim layanan 1 Nov–31 Des 2024; periode test pernah digunakan pada audit sebelumnya, bukan holdout baru. **Target:** biaya verifikasi `FKL48` untuk klaim diterima penuh.

> Visualisasi mengevaluasi estimasi biaya bersyarat pada kode grouper. Model bukan penentu kewajaran klinis, bukan penilai kemampuan bayar pasien, dan bukan detektor fraud tervalidasi. Ketersediaan kode grouper dan tarif pada saat skoring belum terbukti karena timestamp verifikasi tidak tersedia.

## 1. Actual vs Predicted

Hexbin memperlihatkan kepadatan klaim; kedua sumbu biaya dalam skala log dan garis putus-putus menunjukkan prediksi sempurna. Pada reused test: **MAPE 2,12%** dan **MAE Rp46.276**.

![Actual vs Predicted — log-XGBoost](figures/cost_temporal/cost_temporal_actual_vs_predicted.png)

## 2. Learning Curve

MAE train dan validasi ditampilkan dalam rupiah pada setiap boosting round; target training model berskala `log(1 + biaya)`, tetapi metrik early stopping dan kurva ini memakai MAE rupiah. Titik terbaik validasi berada pada **iterasi 2.712**. Kurva ini menggambarkan pemilihan pada validasi internal, bukan bukti generalisasi eksternal.

![Learning Curve — MAE rupiah](figures/cost_temporal/cost_temporal_learning_curve.png)

## 3. Residual Plot

Residual = prediksi − aktual; positif berarti prediksi lebih tinggi. Sumbu vertikal menampilkan 99% residual tengah (|residual| p99 Rp684.959) agar pola utama terbaca; seluruh klaim tetap dihitung dalam metrik keseluruhan. Sebaran melebar pada prediksi lebih tinggi, sehingga klaim mahal tetap memerlukan evaluasi terpisah.

![Residual Plot — log-XGBoost](figures/cost_temporal/cost_temporal_residual_plot.png)

## 4. SHAP Summary

TreeSHAP dihitung pada sampel 1.200 klaim test dan diverifikasi aditif terhadap keluaran model **pada skala log-target**. Jadi sumbu x bukan rupiah. Warna rendah-ke-tinggi hanya dipakai untuk fitur numerik; fitur kategori (INACBG) ditampilkan abu-abu agar urutan kode kategori tidak disalahartikan sebagai besaran ordinal. Rentang sumbu membatasi ekor 1% untuk keterbacaan, bukan menghapusnya dari perhitungan.

![SHAP Summary — log-target](figures/cost_temporal/cost_temporal_shap_summary.png)

Lookup `empirical_tariff` dan kategori INACBG menjadi fitur dengan dampak terbesar pada sampel ini, diikuti severitas dan tipe faskes. SHAP menjelaskan bagaimana model membentuk prediksi, **bukan** mengapa perawatan secara klinis diperlukan atau apakah klaim fraud.

## File dan reproduksi

- Empat PNG terbaru: `docs/figures/cost_temporal/cost_temporal_*.png`.
- Generator: `scripts/bpjs/plot_cost_temporal_audit.py`.
- Model, tabel tarif, konteks fitur, metrik, dan kurva training: artefak lokal ter-ignasi di `backend/app/data/analysis/cost_improvement/`.
- Laporan metodologi/batas penggunaan: [`BPJS_COST_IMPROVEMENT_REPORT.md`](BPJS_COST_IMPROVEMENT_REPORT.md).

Jalankan eksperimen terlebih dahulu untuk membentuk learning history terbaru, lalu `python scripts/bpjs/plot_cost_temporal_audit.py`. Generator memakai bobot kandidat `log_xgb.json`; ia tidak menyentuh bobot runtime.
