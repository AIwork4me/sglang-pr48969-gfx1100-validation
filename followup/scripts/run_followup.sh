#!/usr/bin/env bash
# Follow-up round 2026-11-08: exact invocations (provenance record).
# Environment: the historical W7900 host, unchanged (co-tenant still holding
# 33.26 GB; see followup/evidence_environment/rocm_smi_mem_*.txt). Arm venvs
# and source trees from the historical campaign reused byte-for-byte (gate
# patch re-verified present on PR arm, absent on main before the round).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/followup/scripts/run_env.sh"
cd "$REPO"

# 1) c=1 under the SECOND memory configuration (memfrac 0.30, auto KV pool —
#    the configuration under which the historical c=16 pilot ran):
bash scripts/run_serving_ab.sh A 1 1024 256 1 0.30 A_c1_mem030 0

# 2) c=1 repeat at the original configuration (0.75 + max-total-tokens 100000),
#    independent second ABBA sample for a combined n=4/arm estimate:
bash scripts/run_serving_ab.sh A 1 1024 256 1 0.75 A_c1_rep 100000

# 3) c=2 (crossover-region point, original configuration):
bash scripts/run_serving_ab.sh A 2 1024 256 1 0.75 A_c2 100000

# 4) deterministic-serving verification, both arms
#    (--enable-deterministic-inference; results in followup/evidence_determinism/):
bash followup/scripts/determinism.sh

# 5) metric collection (staging paths shown as executed; artifacts copied into
#    followup/results/):
python3 scripts/collect_metrics.py \
  --perf-dir "$SGLANG_VALIDATION_ROOT/evidence/performance" \
  --out-csv "$SGLANG_VALIDATION_ROOT/results/performance_followup_raw.csv" \
  --out-decode "$SGLANG_VALIDATION_ROOT/results/decode_ms_followup.json"
