import { URL } from 'url';

// In-memory data store for local mock server
let claims = [
  {
    claim_id: 'CLM-DEMO-001',
    patient_id: 'PAT-10023',
    provider_id: 'FAC-B22 (RSUD Cengkareng)',
    doctor_id: 'DR-B22-404',
    diagnosis_primary: 'J18.9', // Pneumonia, unspecified
    diagnosis_secondary: 'A41.9, I10', // Sepsis, Hypertension
    procedure_codes: '89.52, 93.94',
    medication_json: JSON.stringify([{ name: 'Levofloxacin', quantity: 10 }, { name: 'Paracetamol', quantity: 15 }]),
    severity_level: 3,
    cost_claimed: 24500000,
    length_of_stay: 7,
    admission_date: '2026-08-01',
    discharge_date: '2026-08-08',
    status: 'processed',
    risk_score: 72.4,
    priority_tier: 'medium',
    human_decision: null
  },
  {
    claim_id: 'CLM-DEMO-002',
    patient_id: 'PAT-44012',
    provider_id: 'FAC-C19 (RS Siloam)',
    doctor_id: 'DR-C19-112',
    diagnosis_primary: 'I21.9', // Acute myocardial infarction
    diagnosis_secondary: 'I10',
    procedure_codes: '36.12, 89.52',
    medication_json: JSON.stringify([{ name: 'Clopidogrel', quantity: 30 }, { name: 'Atorvastatin', quantity: 30 }]),
    severity_level: 4,
    cost_claimed: 78000000,
    length_of_stay: 10,
    admission_date: '2026-08-05',
    discharge_date: '2026-08-15',
    status: 'processed',
    risk_score: 91.8,
    priority_tier: 'high',
    human_decision: null
  },
  {
    claim_id: 'CLM-DEMO-003',
    patient_id: 'PAT-88129',
    provider_id: 'FAC-A04 (Klinik Bakti)',
    doctor_id: 'DR-A04-001',
    diagnosis_primary: 'E11.9', // Type 2 diabetes mellitus
    diagnosis_secondary: '',
    procedure_codes: '89.07',
    medication_json: JSON.stringify([{ name: 'Metformin', quantity: 30 }]),
    severity_level: 1,
    cost_claimed: 1500000,
    length_of_stay: 0, // Outpatient
    admission_date: '2026-08-10',
    discharge_date: '2026-08-10',
    status: 'processed',
    risk_score: 18.5,
    priority_tier: 'low',
    human_decision: null
  },
  {
    claim_id: 'CLM-DEMO-004',
    patient_id: 'PAT-55312',
    provider_id: 'FAC-B22 (RSUD Cengkareng)',
    doctor_id: 'DR-B22-108',
    diagnosis_primary: 'K29.7', // Gastritis, unspecified
    diagnosis_secondary: '',
    procedure_codes: '',
    medication_json: JSON.stringify([{ name: 'Antasida', quantity: 10 }, { name: 'Omeprazole', quantity: 14 }]),
    severity_level: 1,
    cost_claimed: 2100000,
    length_of_stay: 2,
    admission_date: '2026-08-12',
    discharge_date: '2026-08-14',
    status: 'pending',
    risk_score: null,
    priority_tier: null,
    human_decision: null
  },
  {
    claim_id: 'CLM-DEMO-005',
    patient_id: 'PAT-77291',
    provider_id: 'FAC-D31 (Hermina Arcamanik)',
    doctor_id: 'DR-D31-089',
    diagnosis_primary: 'O80.0', // Spontaneous vertex delivery
    diagnosis_secondary: '',
    procedure_codes: '73.59',
    medication_json: JSON.stringify([{ name: 'Amoxicillin', quantity: 10 }]),
    severity_level: 1,
    cost_claimed: 4500000,
    length_of_stay: 3,
    admission_date: '2026-08-15',
    discharge_date: '2026-08-18',
    status: 'verified',
    risk_score: 22.0,
    priority_tier: 'low',
    human_decision: 'Verified Valid'
  },
  {
    claim_id: 'CLM-DEMO-006',
    patient_id: 'PAT-66102',
    provider_id: 'FAC-C19 (RS Siloam)',
    doctor_id: 'DR-C19-112',
    diagnosis_primary: 'I20.9', // Angina pectoris, unspecified
    diagnosis_secondary: 'I10',
    procedure_codes: '89.52',
    medication_json: JSON.stringify([{ name: 'Isosorbide Dinitrate', quantity: 20 }]),
    severity_level: 2,
    cost_claimed: 18900000,
    length_of_stay: 4,
    admission_date: '2026-08-18',
    discharge_date: '2026-08-22',
    status: 'pending',
    risk_score: null,
    priority_tier: null,
    human_decision: null
  }
];

// Seed other mock databases
let analyses = {};
let decisions = {};

// Pre-fill initial analyses
claims.forEach(c => {
  if (c.status !== 'pending') {
    analyses[c.claim_id] = generateMockAnalysisResult(c);
  }
  if (c.status === 'verified') {
    decisions[c.claim_id] = {
      claim_id: c.claim_id,
      decision: c.human_decision,
      reviewer: 'BPJS-VERIFIER-01',
      timestamp: new Date(Date.now() - 3600000 * 4).toISOString()
    };
  }
});

// Store in-flight analysis tasks
let activeTasks = {};

// Helper to parse JSON body
function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
  });
}

// Generate a highly realistic analysis result dynamically based on claim attributes
function generateMockAnalysisResult(claim) {
  const isHigh = claim.cost_claimed > 50000000 || claim.severity_level >= 4;
  const isMedium = !isHigh && (claim.cost_claimed > 15000000 || claim.severity_level >= 2);

  let score = 15 + Math.floor(Math.random() * 20); // Default low risk score
  let priority = 'low';
  let recommendedAction = 'low_priority';

  if (isHigh) {
    score = 80 + Math.floor(Math.random() * 15);
    priority = 'high';
    recommendedAction = 'verify_immediately';
  } else if (isMedium) {
    score = 55 + Math.floor(Math.random() * 20);
    priority = 'medium';
    recommendedAction = 'review_when_available';
  }

  // Determine anomaly types and explanations
  let clinicalFlags = [];
  let clinicalPlausibility = 'plausible';
  let clinicalEvidence = 'Pola diagnosis primer dan sekunder sejalan dengan penatalaksanaan medis standar.';
  let financialMethod = 'xgboost_regressor';
  let financialDev = (Math.random() * 15) - 5; // -5% to +10%
  let financialEvidence = `Biaya klaim ${fmtRp(claim.cost_claimed)} dalam batas toleransi model finansial.`;
  let fraudIfScore = 0.2 + (Math.random() * 0.3);
  let fraudSimScore = 0.3 + (Math.random() * 0.2);
  let fraudEvidence = 'Pola administrasi wajar dan tidak terdeteksi kemiripan ekstrem dengan pola fraud historis.';
  let similarClaimsList = [];

  if (priority === 'high') {
    clinicalPlausibility = 'implausible';
    clinicalFlags = ['secondary_diag_severity_mismatch', 'procedure_mismatch'];
    clinicalEvidence = `Ketidakcocokan keparahan diagnosis (Severity Level ${claim.severity_level}) dengan prosedur ${claim.procedure_codes || 'tanpa tindakan bedah mayor'}. Rekomendasi audit rekam medis.`;
    financialDev = 30 + (Math.random() * 40); // 30% to 70% deviation
    financialEvidence = `Biaya diklaim ${fmtRp(claim.cost_claimed)} terpaut +${financialDev.toFixed(1)}% di atas prediksi XGBoost untuk diagnosis ${claim.diagnosis_primary}.`;
    fraudIfScore = 0.75 + (Math.random() * 0.15);
    fraudSimScore = 0.82 + (Math.random() * 0.12);
    fraudEvidence = `Terdeteksi anomali multi-faktor (IF Score: ${(fraudIfScore*100).toFixed(0)}%). Kode medis dan rasio biaya memiliki kecocokan pola tinggi (${(fraudSimScore*100).toFixed(0)}%) dengan kasus fraud terbukti sebelumnya.`;

    similarClaimsList = [
      {
        claim_id: `CLM-HIST-${1000 + Math.floor(Math.random()*9000)}`,
        diagnosis_primary: claim.diagnosis_primary,
        cost_claimed: claim.cost_claimed * 0.96,
        similarity: fraudSimScore,
        code_similarity: 0.95,
        cost_proximity: 0.98,
        same_provider: true,
        same_patient: false,
        days_apart: 14
      },
      {
        claim_id: `CLM-HIST-${1000 + Math.floor(Math.random()*9000)}`,
        diagnosis_primary: claim.diagnosis_primary,
        cost_claimed: claim.cost_claimed * 1.05,
        similarity: fraudSimScore - 0.1,
        code_similarity: 0.88,
        cost_proximity: 0.90,
        same_provider: false,
        same_patient: false,
        days_apart: 30
      }
    ];
  } else if (priority === 'medium') {
    clinicalPlausibility = 'questionable';
    clinicalFlags = ['severity_med_mismatch'];
    clinicalEvidence = `Pemberian obat melebihi standar untuk tingkat keparahan sedang. Harap evaluasi resep.`;
    financialDev = 15 + (Math.random() * 20); // 15% to 35%
    financialEvidence = `Biaya diklaim ${fmtRp(claim.cost_claimed)} terpaut +${financialDev.toFixed(1)}% di atas peers.`;
    fraudIfScore = 0.55 + (Math.random() * 0.15);
    fraudSimScore = 0.65 + (Math.random() * 0.15);
    fraudEvidence = 'Terdapat anomali biaya dan durasi rawat sedang. Kemiripan dengan pola kloning historis marginal.';
  }

  // Risk score breakdown
  const clinicalScoreWeight = priority === 'high' ? 30 : (priority === 'medium' ? 15 : 5);
  const financialScoreWeight = priority === 'high' ? 35 : (priority === 'medium' ? 20 : 5);
  const isolationScoreWeight = priority === 'high' ? 15 : (priority === 'medium' ? 10 : 3);
  const similarityScoreWeight = priority === 'high' ? 20 : (priority === 'medium' ? 10 : 2);
  const totalScoreCalc = clinicalScoreWeight + financialScoreWeight + isolationScoreWeight + similarityScoreWeight;

  return {
    analysis_version: 3,
    clinical: {
      plausibility: clinicalPlausibility,
      evidence_source: 'llm_local',
      model_used: 'mistral-7b',
      rule_flags: clinicalFlags,
      grouper_result: {
        cbg_code: claim.diagnosis_primary.startsWith('I') ? 'I-4-10-I' : 'J-4-15-II',
        cbg_name: claim.diagnosis_primary.startsWith('I') ? 'Penyakit Jantung Akut' : 'Infeksi Saluran Pernapasan'
      },
      tariff_deviation_pct: financialDev * 0.8,
      evidence_text: clinicalEvidence
    },
    financial: {
      method: financialMethod,
      deviation_pct: financialDev,
      anomaly_score: financialDev / 100,
      shap_top_features: [
        { feature_name: 'cost_vs_peer_ratio', contribution: financialDev * 0.3, direction: 'positive', feature_label: 'Rasio biaya vs rata-rata peer' },
        { feature_name: 'severity_proc_mismatch', contribution: financialDev * 0.2, direction: 'positive', feature_label: 'Severity vs Prosedur tidak cocok' },
        { feature_name: 'length_of_stay', contribution: financialDev * 0.1, direction: 'positive', feature_label: 'Lama rawat (LOS) outlier' }
      ],
      evidence_text: financialEvidence
    },
    fraud: {
      isolation_forest_score: fraudIfScore,
      similarity_max_score: fraudSimScore,
      repeat_billing_flag: priority === 'high' && Math.random() > 0.7,
      graph_cluster_anomaly_score: fraudIfScore * 0.8,
      evidence_text: fraudEvidence,
      similar_claims: similarClaimsList
    },
    review: {
      evidence_level: priority === 'high' ? 'strong_multi_signal' : (priority === 'medium' ? 'single_signal' : 'weak'),
      reasoning_source: 'llm_local',
      model_used: 'deepseek-r1-1.5b',
      corroborating_signals: priority === 'high' ? ['Penyimpangan Finansial', 'Ketidaksesuaian Keparahan', 'Kemiripan Historis'] : (priority === 'medium' ? ['Penyimpangan Finansial'] : []),
      reasoning_narrative: priority === 'high'
        ? `Klaim CLM-DEMO menunjukkan pola penyimpangan yang sangat mirip dengan modus operandi upcoding. Terdapat ketidakwajaran klinis antara keparahan keluhan dengan tindakan yang dilakukan.`
        : (priority === 'medium' ? `Ditemukan deviasi biaya moderat dibandingkan peer faskes untuk diagnosis yang sama.` : `Klaim tergolong wajar dan bersih dari indikasi anomali sistem.`)
    },
    risk: {
      total_score: totalScoreCalc,
      priority_tier: priority,
      breakdown: {
        clinical_rule_flags: clinicalScoreWeight,
        financial_anomaly: financialScoreWeight,
        isolation_forest_anomaly: isolationScoreWeight,
        similarity_fraud: similarityScoreWeight,
        synthesis_confidence: 0
      }
    },
    explanation: {
      narrative_id: priority === 'high'
        ? `Klaim ${claim.claim_id} dari faskes ${claim.provider_id} menunjukkan indikasi ketidakwajaran finansial berat (+${financialDev.toFixed(0)}%) disertai profil diagnosis yang kurang didukung bukti klinis. Direkomendasikan penundaan pembayaran untuk audit berkas.`
        : (priority === 'medium' ? `Klaim ${claim.claim_id} memiliki deviasi biaya moderat. Disarankan verifikasi administratif.` : `Klaim ${claim.claim_id} berjalan sesuai parameter standar JKN. Dapat diproses rutin.`),
      recommended_action: recommendedAction,
      generated_by: 'mistral-7b',
      qa_panel: {
        why_top_priority: priority === 'high' ? 'Karena memiliki skor deviasi biaya ekstrem dan terdeteksi ketidakcocokan tindakan klinis.' : 'Biaya dan pola klinis tergolong standar, masuk dalam prioritas rendah.',
        strongest_evidence: priority === 'high' ? `Nominal klaim ${fmtRp(claim.cost_claimed)} melampaui rata-rata peer sebesar +${financialDev.toFixed(0)}% untuk pasien diagnosis ${claim.diagnosis_primary}.` : 'Tidak ada temuan anomali finansial signifikan.',
        most_similar_claim: similarClaimsList.length > 0 ? `Kemiripan ${(fraudSimScore*100).toFixed(0)}% dengan klaim historis ${similarClaimsList[0].claim_id} di faskes yang sama.` : 'Tidak ditemukan klaim serupa dengan tingkat kemiripan di atas ambang deteksi.',
        is_this_fraud: priority === 'high' ? 'Sistem memberikan probabilitas anomali tinggi. Pembuktian legal fraud memerlukan verifikasi dokumen pendukung medis oleh verifikator.' : 'Sangat kecil kemungkinan fraud. Data sesuai sebaran normal.'
      }
    }
  };
}

function fmtRp(x) {
  return `Rp ${(x || 0).toLocaleString('id-ID')}`;
}

export function mockApiPlugin() {
  return {
    name: 'mock-api-plugin',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const parsedUrl = new URL(req.url, 'http://localhost');
        const path = parsedUrl.pathname;

        // Intercept only /api routes
        if (!path.startsWith('/api')) {
          return next();
        }

        // Set common response headers
        res.setHeader('Content-Type', 'application/json');

        // Route mapping
        try {
          // 1. GET /api/analytics/dashboard
          if (path === '/api/analytics/dashboard' && req.method === 'GET') {
            const total = claims.length;
            const processed = claims.filter(c => c.status !== 'pending').length;
            const verified = claims.filter(c => c.status === 'verified').length;
            const pending = claims.filter(c => c.status === 'pending').length;

            const high = claims.filter(c => c.status !== 'pending' && c.priority_tier === 'high').length;
            const medium = claims.filter(c => c.status !== 'pending' && c.priority_tier === 'medium').length;
            const low = claims.filter(c => c.status !== 'pending' && c.priority_tier === 'low').length;

            // Calculate potential savings: sum of deviation for high & medium claims
            let savings = 0;
            claims.forEach(c => {
              if (c.status !== 'pending' && (c.priority_tier === 'high' || c.priority_tier === 'medium')) {
                savings += Math.round(c.cost_claimed * 0.22); // average savings factor
              }
            });

            res.end(JSON.stringify({
              total_claims: total,
              processed_claims: processed,
              high_risk_claims: high,
              medium_risk_claims: medium,
              low_risk_claims: low,
              verified_claims: verified,
              pending_claims: pending,
              potential_savings: savings
            }));
            return;
          }

          // 2. GET /api/health
          if (path === '/api/health' && req.method === 'GET') {
            res.end(JSON.stringify({
              status: 'ok',
              components: {
                database: { status: 'ok', detail: 'PostgreSQL terhubung (Mocked)' },
                llm_ollama: { status: 'ok', detail: '1 model tersedia: mistral-7b (Mocked)' },
                ml_financial: { status: 'ok', detail: 'XGBoost + SHAP termuat (Mocked)' },
                ml_isolation_forest: { status: 'ok', detail: 'termuat (Mocked)' },
                vector_store: { status: 'ok', detail: `LanceDB ${claims.length * 12} vektor (Mocked)` },
                graph_metrics: { status: 'ok', detail: '3 provider terindeks (Mocked)' }
              }
            }));
            return;
          }

          // 3. GET /api/ml/eval
          if (path === '/api/ml/eval' && req.method === 'GET') {
            res.end(JSON.stringify({
              generated_from: 'mock-server',
              dataset: {
                total_samples: 1250,
                train_size: 800,
                val_size: 200,
                test_size: 250,
                fraud_rate: 0.12
              },
              xgboost_regressor: {
                mape_pct_normal_holdout: 4.8
              },
              xgboost_classifier: {
                precision: 0.892,
                recall: 0.841,
                f1: 0.865,
                roc_auc: 0.942,
                pr_auc: 0.915
              },
              logistic_regression_baseline: {
                precision: 0.725,
                recall: 0.680,
                f1: 0.702,
                roc_auc: 0.812,
                pr_auc: 0.756
              },
              recall_per_anomaly_type: {
                upcoding: { recall: 0.91, count: 42 },
                phantom_billing: { recall: 0.88, count: 25 },
                repeat_billing: { recall: 0.40, count: 20 },
                cloning: { recall: 0.35, count: 18 },
                prolonged_los: { recall: 0.82, count: 30 },
                inflated_bill: { recall: 0.89, count: 32 },
                unbundling: { recall: 0.78, count: 15 }
              },
              isolation_forest: {
                detection_rate_anomalies: 0.712,
                false_positive_rate_normal: 0.084
              },
              feature_importance: {
                cost_vs_peer_ratio: 0.342,
                severity_proc_mismatch: 0.221,
                length_of_stay: 0.158,
                num_medications: 0.095,
                has_high_cost_proc: 0.082,
                num_secondary_diags: 0.062,
                has_upcoding_risk_diag: 0.040
              }
            }));
            return;
          }

          // 4. GET /api/claims
          if (path === '/api/claims' && req.method === 'GET') {
            const queryParams = parsedUrl.searchParams;
            const skip = parseInt(queryParams.get('skip') || '0', 10);
            const limit = parseInt(queryParams.get('limit') || '25', 10);
            const q = (queryParams.get('q') || '').toLowerCase().trim();
            const statusFilter = queryParams.get('status') || '';
            const tierFilter = queryParams.get('tier') || '';
            const sort = queryParams.get('sort') || 'priority';

            // Filter
            let filtered = claims.filter(c => {
              // Q filter
              if (q) {
                const matchId = c.claim_id.toLowerCase().includes(q);
                const matchPatient = c.patient_id.toLowerCase().includes(q);
                const matchProvider = c.provider_id.toLowerCase().includes(q);
                const matchDiag = c.diagnosis_primary.toLowerCase().includes(q);
                if (!matchId && !matchPatient && !matchProvider && !matchDiag) {
                  return false;
                }
              }
              // Status filter
              if (statusFilter && c.status !== statusFilter) {
                return false;
              }
              // Tier filter
              if (tierFilter && c.priority_tier !== tierFilter) {
                return false;
              }
              return true;
            });

            // Sort
            filtered.sort((a, b) => {
              if (sort === 'priority') {
                const tierWeights = { high: 3, medium: 2, low: 1, null: 0, undefined: 0 };
                const wA = tierWeights[a.priority_tier] || 0;
                const wB = tierWeights[b.priority_tier] || 0;
                if (wA !== wB) return wB - wA;
                // subsort pending to the bottom
                if (a.status === 'pending' && b.status !== 'pending') return 1;
                if (b.status === 'pending' && a.status !== 'pending') return -1;
                return b.cost_claimed - a.cost_claimed;
              }
              if (sort === 'risk_desc') {
                return (b.risk_score || 0) - (a.risk_score || 0);
              }
              if (sort === 'risk_asc') {
                return (a.risk_score || 0) - (b.risk_score || 0);
              }
              if (sort === 'cost_desc') {
                return b.cost_claimed - a.cost_claimed;
              }
              if (sort === 'cost_asc') {
                return a.cost_claimed - b.cost_claimed;
              }
              if (sort === 'id') {
                return a.claim_id.localeCompare(b.claim_id);
              }
              return 0;
            });

            const paginated = filtered.slice(skip, skip + limit);
            res.end(JSON.stringify({
              total: filtered.length,
              items: paginated
            }));
            return;
          }

          // 5. POST /api/claims (Insert manual claim)
          if (path === '/api/claims' && req.method === 'POST') {
            const body = await readRequestBody(req);

            // Validate client logic
            if (!body.claim_id || !body.patient_id || !body.provider_id || !body.diagnosis_primary) {
              res.statusCode = 400;
              res.end(JSON.stringify({ detail: 'Kolom wajib diisi kurang lengkap.' }));
              return;
            }

            // Check duplicate
            if (claims.some(c => c.claim_id === body.claim_id)) {
              res.statusCode = 400;
              res.end(JSON.stringify({ detail: `Claim ID ${body.claim_id} sudah ada di database.` }));
              return;
            }

            const newClaim = {
              claim_id: body.claim_id,
              patient_id: body.patient_id,
              provider_id: body.provider_id + ' (Manual Intake)',
              doctor_id: body.doctor_id || 'DR-GENERIC',
              diagnosis_primary: body.diagnosis_primary,
              diagnosis_secondary: (body.diagnosis_secondary || []).join(', '),
              procedure_codes: (body.procedure_codes || []).join(', '),
              medication_json: JSON.stringify(body.medication || []),
              severity_level: body.severity_level || 1,
              cost_claimed: body.cost_claimed || 1000000,
              length_of_stay: body.length_of_stay || 1,
              admission_date: body.admission_date || new Date().toISOString().split('T')[0],
              discharge_date: body.discharge_date || new Date().toISOString().split('T')[0],
              status: 'pending',
              risk_score: null,
              priority_tier: null,
              human_decision: null
            };

            claims.push(newClaim);
            res.end(JSON.stringify({
              status: 'success',
              message: 'Klaim berhasil dimasukkan ke antrean.',
              claim_id: body.claim_id
            }));
            return;
          }

          // 6. POST /api/claims/analyze (Trigger analysis task)
          if (path === '/api/claims/analyze' && req.method === 'POST') {
            const body = await readRequestBody(req);
            const claimId = body.claim_id;

            const claim = claims.find(c => c.claim_id === claimId);
            if (!claim) {
              res.statusCode = 404;
              res.end(JSON.stringify({ detail: `Klaim ${claimId} tidak ditemukan.` }));
              return;
            }

            const taskId = `task-${Math.random().toString(36).substring(2, 11)}`;
            activeTasks[taskId] = claimId;

            res.end(JSON.stringify({
              task_id: taskId,
              status: 'started'
            }));
            return;
          }

          // 7. GET /api/stream/:taskId (SSE Stream for claim analysis)
          if (path.startsWith('/api/stream/') && req.method === 'GET') {
            const taskId = path.split('/').pop();
            const claimId = activeTasks[taskId];
            const claim = claims.find(c => c.claim_id === claimId);

            if (!claim) {
              res.statusCode = 404;
              res.end(JSON.stringify({ detail: 'Task atau klaim tidak ditemukan.' }));
              return;
            }

            // Setup EventStream headers
            res.writeHead(200, {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
              'Connection': 'keep-alive',
              'Access-Control-Allow-Origin': '*'
            });

            // Write SSE event helper
            const sendEvent = (event, data) => {
              res.write(`event: ${event}\n`);
              res.write(`data: ${JSON.stringify(data)}\n\n`);
            };

            // Generate the analysis on the fly
            const mockAnalysis = generateMockAnalysisResult(claim);

            let step = 0;
            const interval = setInterval(() => {
              step++;
              if (step === 1) {
                sendEvent('status', { step: 'validation', message: 'Validasi deterministik selesai. 0 error ditemukan.' });
              } else if (step === 2) {
                sendEvent('status', { step: 'phase1', message: 'Menjalankan Clinical Agent, Financial Agent, & Fraud Agent secara paralel...' });
              } else if (step === 3) {
                sendEvent('phase1_complete', {
                  clinical: mockAnalysis.clinical,
                  financial: mockAnalysis.financial,
                  fraud: mockAnalysis.fraud,
                  partial: false
                });
              } else if (step === 4) {
                sendEvent('status', { step: 'phase2', message: 'Menjalankan Synthesis Agent untuk merangkum temuan bukti...' });
              } else if (step === 5) {
                sendEvent('phase2_complete', {
                  review: mockAnalysis.review
                });
              } else if (step === 6) {
                sendEvent('status', { step: 'phase3', message: 'Menjalankan Risk Score Engine deterministik...' });
              } else if (step === 7) {
                sendEvent('phase3_complete', {
                  risk: mockAnalysis.risk
                });
              } else if (step === 8) {
                sendEvent('status', { step: 'phase4', message: 'Menjalankan Explanation Agent untuk menyusun narasi ringkasan...' });
              } else if (step === 9) {
                sendEvent('phase4_complete', {
                  explanation: mockAnalysis.explanation
                });
              } else if (step === 10) {
                // Finalize claim status in memory database
                claim.status = 'processed';
                claim.risk_score = mockAnalysis.risk.total_score;
                claim.priority_tier = mockAnalysis.risk.priority_tier;
                analyses[claimId] = mockAnalysis;

                res.write(`event: done\ndata: Investigation complete\n\n`);
                clearInterval(interval);
                res.end();
              }
            }, 600); // 600ms per phase to show beautiful UI timeline ticks

            req.on('close', () => {
              clearInterval(interval);
            });
            return;
          }

          // 8. GET /api/claims/:id/analysis
          if (path.endsWith('/analysis') && req.method === 'GET') {
            const claimId = path.split('/')[3];
            const analysis = analyses[claimId];

            if (!analysis) {
              res.statusCode = 404;
              res.end(JSON.stringify({ detail: 'Analisis belum dibuat untuk klaim ini.' }));
              return;
            }

            res.end(JSON.stringify({
              status: 'analyzed',
              result: analysis
            }));
            return;
          }

          // 9. GET /api/claims/:id/decision
          if (path.endsWith('/decision') && req.method === 'GET') {
            const claimId = path.split('/')[3];
            const decision = decisions[claimId];

            if (!decision) {
              res.end(JSON.stringify({ status: 'pending' }));
              return;
            }

            res.end(JSON.stringify({
              status: 'decided',
              decision: decision.decision,
              reviewer: decision.reviewer,
              timestamp: decision.timestamp
            }));
            return;
          }

          // 10. POST /api/claims/:id/decision
          if (path.endsWith('/decision') && req.method === 'POST') {
            const claimId = path.split('/')[3];
            const body = await readRequestBody(req);

            decisions[claimId] = {
              claim_id: claimId,
              decision: body.decision,
              reviewer: body.reviewer || 'BPJS-VERIFIER-01',
              timestamp: new Date().toISOString()
            };

            // Update status
            const claim = claims.find(c => c.claim_id === claimId);
            if (claim) {
              claim.status = 'verified';
              claim.human_decision = body.decision;
            }

            res.end(JSON.stringify({ status: 'success' }));
            return;
          }

          // 11. GET /api/claims/:id (Individual claim details)
          const individualClaimMatch = path.match(/^\/api\/claims\/([^\/]+)$/);
          if (individualClaimMatch && req.method === 'GET') {
            const claimId = individualClaimMatch[1];
            const claim = claims.find(c => c.claim_id === claimId);
            if (!claim) {
              res.statusCode = 404;
              res.end(JSON.stringify({ detail: `Klaim ${claimId} tidak ditemukan.` }));
              return;
            }
            res.end(JSON.stringify(claim));
            return;
          }

          // 12. DELETE /api/claims/:id (Reset / delete analysis)
          if (individualClaimMatch && req.method === 'DELETE') {
            const claimId = individualClaimMatch[1];
            const claim = claims.find(c => c.claim_id === claimId);
            if (claim) {
              claim.status = 'pending';
              claim.risk_score = null;
              claim.priority_tier = null;
              claim.human_decision = null;
              delete analyses[claimId];
              delete decisions[claimId];
            }
            res.end(JSON.stringify({ status: 'success' }));
            return;
          }

          // 13. POST /api/demo/generate (Trigger demo generator)
          if (path === '/api/demo/generate' && req.method === 'POST') {
            res.end(JSON.stringify({ status: 'started' }));
            return;
          }

          // 14. GET /api/demo/stream (SSE Stream for demo loader progress)
          if (path === '/api/demo/stream' && req.method === 'GET') {
            res.writeHead(200, {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
              'Connection': 'keep-alive',
              'Access-Control-Allow-Origin': '*'
            });

            const sendEvent = (event, data) => {
              res.write(`event: ${event}\n`);
              res.write(`data: ${JSON.stringify(data)}\n\n`);
            };

            let step = 0;
            const totalClaims = 80;
            const interval = setInterval(() => {
              step++;
              if (step === 1) {
                sendEvent('status', 'Membaca template tarif INA-CBG...');
              } else if (step === 2) {
                sendEvent('status', 'Men-generate 80 sampel klaim sintetis...');
              } else if (step <= 6) {
                const current = Math.floor((step - 2) * (totalClaims / 4));
                sendEvent('progress', { current, total: totalClaims });
              } else if (step === 7) {
                sendEvent('status', 'Menyimpan 80 klaim buatan ke database...');
              } else if (step === 8) {
                sendEvent('status', 'Mengindeks vektor kemiripan baru di LanceDB...');
              } else if (step === 9) {
                sendEvent('status', 'Me-refresh grafik jaringan metrik faskes...');
              } else if (step === 10) {
                // Insert 6 new realistic demo claims to front of array to see them populate
                const demoItems = [
                  {
                    claim_id: 'CLM-DEMO-GEN-01',
                    patient_id: 'PAT-40292',
                    provider_id: 'FAC-A12 (Klinik Medika)',
                    doctor_id: 'DR-A12-004',
                    diagnosis_primary: 'I21.9',
                    diagnosis_secondary: 'I10',
                    procedure_codes: '36.12, 89.52',
                    medication_json: JSON.stringify([{ name: 'Clopidogrel', quantity: 30 }]),
                    severity_level: 4,
                    cost_claimed: 61500000,
                    length_of_stay: 8,
                    admission_date: '2026-08-20',
                    discharge_date: '2026-08-28',
                    status: 'pending',
                    risk_score: null,
                    priority_tier: null,
                    human_decision: null
                  },
                  {
                    claim_id: 'CLM-DEMO-GEN-02',
                    patient_id: 'PAT-28101',
                    provider_id: 'FAC-B22 (RSUD Cengkareng)',
                    doctor_id: 'DR-B22-201',
                    diagnosis_primary: 'J18.9',
                    diagnosis_secondary: 'A41.9',
                    procedure_codes: '93.94',
                    medication_json: JSON.stringify([{ name: 'Ceftriaxone', quantity: 14 }]),
                    severity_level: 3,
                    cost_claimed: 29000000,
                    length_of_stay: 6,
                    admission_date: '2026-08-22',
                    discharge_date: '2026-08-28',
                    status: 'pending',
                    risk_score: null,
                    priority_tier: null,
                    human_decision: null
                  },
                  {
                    claim_id: 'CLM-DEMO-GEN-03',
                    patient_id: 'PAT-90182',
                    provider_id: 'FAC-C19 (RS Siloam)',
                    doctor_id: 'DR-C19-099',
                    diagnosis_primary: 'E11.9',
                    diagnosis_secondary: '',
                    procedure_codes: '',
                    medication_json: JSON.stringify([{ name: 'Metformin', quantity: 30 }]),
                    severity_level: 1,
                    cost_claimed: 1200000,
                    length_of_stay: 0,
                    admission_date: '2026-08-25',
                    discharge_date: '2026-08-25',
                    status: 'pending',
                    risk_score: null,
                    priority_tier: null,
                    human_decision: null
                  }
                ];

                // Check and push to prevent duplicate seeds
                demoItems.forEach(di => {
                  if (!claims.some(c => c.claim_id === di.claim_id)) {
                    claims.unshift(di); // Put on top of array
                  }
                });

                sendEvent('done', 'Generasi selesai — 3 klaim baru dimasukkan ke antrean teratas.');
                clearInterval(interval);
                res.end();
              }
            }, 500);

            req.on('close', () => {
              clearInterval(interval);
            });
            return;
          }

          // If no matching endpoint found
          res.statusCode = 404;
          res.end(JSON.stringify({ detail: `Mock endpoint ${req.method} ${path} tidak ditemukan.` }));
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ detail: `Mock Server Error: ${e.message}` }));
        }
      });
    }
  };
}
