# Audit dan eksperimen ulang kandidat biaya BPJS

**Status: eksperimen offline, bukan model runtime dan bukan validasi fraud.**

Skrip: `scripts/bpjs/cost_temporal_audit.py`. Artefak lokal ter-ignasi: `backend/app/data/analysis/cost_temporal_audit/`. Sumber: sampel Reguler FKRTL; target biaya verifikasi `FKL48`, filter `FKL47 == FKL48 > 0`, LOS 0–365 hari dan INACBG terisi. Tidak ada oversampling atau pembobotan sampel.

## Desain

- Tanggal awal layanan sebelum 1 November 2024 dan hash peserta bucket 0–5: fit **851.350** klaim, 163.848 peserta.
- Periode yang sama dan bucket 6–7: validasi **284.303** klaim, 54.477 peserta.
- Tanggal awal layanan 1 November–31 Desember 2024 dan bucket 8–9: test **56.385** klaim, 21.559 peserta. Sebanyak 505.550 klaim di luar kombinasi ini tidak digunakan. Interseksi peserta antarketiga split = 0.
- Tabel median INACBG × severitas menggunakan fit saja. Pada fit, fitur median dibuat secara cross-fit lima kelompok peserta; validasi/test memakai tabel fit penuh. Grup yang tak dikenal memakai median global fit Rp200.600. Enam klaim test memiliki grup tarif tak dikenal.
- Diagnosis dikodekan dengan kamus yang dibangun dari diagnosis fit, dengan -1 untuk kode yang tak dikenal; 32 klaim test mempunyai diagnosis tak dikenal. Berbeda dari skrip lama, tidak ada fallback diam-diam ke katalog kosong. Model tersimpan memang menggunakan fitur diagnosis.
- Training XGBoost menggunakan validation MAE dan early stopping 25 putaran, maksimal 400; hasil: 400 pohon dengan tarif (batas maksimum tercapai), 372 tanpa tarif. Evaluasi memakai model yang dipotong pada iterasi terbaik. Pembanding median menggunakan data dan split yang sama.
- Potongan waktu menggunakan **tanggal awal layanan**, bukan tanggal saat biaya verifikasi tersedia. Sebagian layanan sebelum cutoff mungkin baru selesai atau diverifikasi sesudah cutoff; ini bukan simulasi sempurna atas ketersediaan informasi pada tanggal tersebut.

## Hasil test temporal

| Pendekatan | MAPE | MedAPE | MAE | RMSE | R² | Dalam ±10% |
|---|---:|---:|---:|---:|---:|---:|
| Median INACBG × severitas | **6,57%** | **2,47%** | Rp137.902 | Rp1.126.544 | 0,8731 | 84,47% |
| XGBoost dengan median tarif | 6,95% | 3,31% | **Rp79.735** | **Rp861.948** | **0,9257** | **84,90%** |
| XGBoost tanpa median tarif | 39,98% | 14,98% | Rp359.560 | Rp2.119.773 | 0,5506 | 42,03% |

Validasi, sebelum melihat test: MAPE median 6,49% vs XGBoost dengan tarif 7,05%; MAE median Rp135.017 vs XGBoost Rp77.632. Tidak ada pemenang di semua metrik. Ablasi menghapus median, bukan seluruh informasi yang berkaitan dengan INACBG: severitas dan fitur lain tetap ada.

## Strata test

| Kelompok | n | Median MAPE / MAE | XGBoost dengan tarif MAPE / MAE | XGBoost ±10% |
|---|---:|---:|---:|---:|
| Dialisis | 26.678 | 5,55% / Rp31.827 | 5,75% / Rp21.234 | 90,89% |
| Non-dialisis | 29.707 | 7,48% / Rp233.161 | 8,03% / Rp132.271 | 79,52% |
| Biaya >Rp20 juta | 153 | 26,63% / Rp11.865.408 | 14,66% / Rp7.756.036 | 47,06% |

Hasil kelompok >Rp20 juta berdasarkan 153 klaim, sehingga ketidakpastiannya besar. XGBoost dengan tarif menghasilkan 0 prediksi negatif pada test, tetapi **7 pada validation**; tidak boleh dianggap dijamin positif. Prediksi belum diklip.

## Interpretasi dan keterbatasan

1. Perbandingan lama memakai split dan fitur berbeda; angka lama dan baru **bukan estimasi peningkatan kausal yang setara**. Parity metrik dari model tersimpan telah diperiksa ulang dan cocok persis, tetapi bukan validasi independen.
2. Pengaruh tabel median sangat besar. Dengan tarif, model memprediksi biaya terverifikasi berdasarkan grup yang sudah ditentukan; bila INACBG/severitas yang diinput salah atau dimanipulasi, benchmark dapat mengikuti kesalahan itu. Hasil ini tidak menunjukkan kemampuan mendeteksi upcoding.
3. Hanya tanggal awal layanan tersedia dalam eksperimen ini; kapan verifikasi dan semua fitur tersedia di sistem nyata belum dipastikan. Kode diagnosis yang dipakai adalah diagnosis masuk tiga digit, bukan otomatis diagnosis akhir E-Klaim. Kelas rawat bukan kelas rumah sakit; prosedur hanya indikator ada/tidak.
4. Sampel BPJS tidak memiliki label fraud terkonfirmasi; biaya yang diterima penuh bukan bukti klaim bebas anomali. Tidak ada evaluasi precision/recall fraud atau validasi eksternal rumah sakit, dan tidak ada inferensi representativitas nasional karena bobot survei tidak digunakan.
5. Test merupakan subset peserta hash 8–9 yang berkunjung pada periode akhir, bukan seluruh klaim akhir. Validasi berasal dari periode sebelum cutoff dengan peserta berbeda; tidak ada validasi temporal terpisah kedua.
6. Model memiliki MAE dan RMSE lebih baik dalam eksperimen ini, tetapi median memiliki MAPE/MedAPE lebih baik. Pilihan tergantung fungsi biaya dan kebutuhan reviewer; model tidak otomatis layak dipromosikan.

## Keputusan

Pertahankan model ini sebagai **kandidat offline**. Jangan mengganti model runtime tanpa kontrak input E-Klaim yang diuji, verifikasi waktu ketersediaan fitur dan label, evaluasi eksternal, penanganan prediksi tidak valid, dan kalibrasi ambang berdasarkan review ahli. Simpan baseline median sebagai pembanding wajib. Isolation Forest belum dilatih ulang dalam eksperimen ini.
