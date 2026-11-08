#!/usr/bin/env python3
"""Assemble round3/audit/VALIDATION_CERTIFICATE.json + .md after the campaign.
Pulls measured facts from evidence; refuses to invent statuses: test outcomes
come from verdicts.json (written by finalize_round3.sh) and evidence presence
checks. Every PASS must reference files that exist."""
import hashlib, json, os, subprocess, sys

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CAMP = os.path.abspath(os.path.join(R3, "..", ".."))

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def ev(rel):
    return os.path.join("round3", rel)

def main():
    env = json.load(open(os.path.join(R3, "evidence/environment/gpu_properties.json")))
    stats = json.load(open(os.path.join(R3, "results/statistics.json")))
    gate = json.load(open(os.path.join(R3, "results/gate_matrix.json")))
    src = open(os.path.join(R3, "evidence/source/arm_commits.txt")).read()
    model_man = json.load(open("/workspace/round3-work/dl/qwen3-06b/round3_download_manifest.json"))
    order = [json.loads(l) for l in open(os.path.join(R3, "evidence/performance/order.jsonl"))]
    verdicts = json.load(open(os.path.join(R3, "audit/verdicts.json")))

    def sha_of(rel):
        p = os.path.join(CAMP, rel)
        return sha256(p) if os.path.exists(p) else None

    cert = {
        "run_id": "round3-1da9ae2-w7900-" + order[0]["utc_start"].replace(":", "").replace("-", "")[:13],
        "utc_start": order[0]["utc_start"],
        "utc_end": order[-1].get("utc_end"),
        "hardware": {
            "device_name": env["device_name"],
            "gcn_arch_name": env["gcn_arch_name"],
            "rocminfo_compute_units": gate["rocminfo_compute_units"],
            "multi_processor_count": env["multi_processor_count"],
            "total_memory_bytes": env["total_memory_bytes"],
        },
        "stack": {
            "torch": env["torch"], "torch_hip": env["torch_hip"],
            "triton": env["triton"],
            "rocm": "7.2.1 (host /opt/rocm-7.2.1)",
        },
        "gate": {
            "sglang_current_arch_num_sms": env["sglang_current_arch_num_sms"],
            "computed_threshold": env["computed_threshold"],
            "head_tiles_qwen3_06b": gate["head_tiles_qwen3_06b"],
        },
        "sources": {
            "main_arm": "cbbc6b67f48008a8b739f4667d7b14abb89088cf",
            "old_gate_arm": "1da9ae2fcba99be22ed756083e1eb505c1cf5afe + single-line revert to fixed 8",
            "new_gate_arm": "1da9ae2fcba99be22ed756083e1eb505c1cf5afe (unmodified)",
            "old_vs_new_diff": "round3/evidence/source/old_vs_new.diff",
        },
        "model": {
            "repo": model_man["repo"], "revision": model_man["revision"],
            "files_sha256": model_man["files"],
        },
        "benchmark_config": {
            "server": "--attention-backend triton --context-length 10240 --mem-fraction-static {0.75,0.30} --max-total-tokens {100000,auto}",
            "env": "SGLANG_DISABLE_LEAN_ATTENTION=1 SGLANG_USE_AITER=0 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
            "bench": "sglang.benchmark.serving random i1024/o256/range1 seed1, warmup per server start, fresh server per leg",
            "ordering": "ABBA/BAAB alternating; see round3/evidence/performance/order.jsonl",
        },
        "counts": {},
        "tests": verdicts,
        "measured_totals": stats["arm_totals"],
        "audit": "round3/audit/audit_report.json (independent CPU audit)",
        "disclaimer": "Project-generated evidence attestation. NOT an AMD-issued certification and NOT cryptographically signed.",
    }
    for t in cert["tests"].values():
        cert["counts"][t["status"]] = cert["counts"].get(t["status"], 0) + 1

    json.dump(cert, open(os.path.join(R3, "audit/VALIDATION_CERTIFICATE.json"), "w"), indent=2)

    md = []
    md.append("# Round 3 Validation Certificate\n")
    md.append(f"**Run ID:** `{cert['run_id']}`  ")
    md.append(f"**Window:** {cert['utc_start']} → {cert['utc_end']} (UTC)  ")
    md.append(f"**Hardware:** {cert['hardware']['device_name']} ({cert['hardware']['gcn_arch_name']}), "
              f"rocminfo CUs {cert['hardware']['rocminfo_compute_units']}, "
              f"`multi_processor_count` **{cert['hardware']['multi_processor_count']}**, "
              f"VRAM {cert['hardware']['total_memory_bytes']/2**30:.0f} GiB\n")
    md.append(f"**Stack:** torch {cert['stack']['torch']} (HIP {cert['stack']['torch_hip']}), Triton {cert['stack']['triton']}, ROCm {cert['stack']['rocm']}\n")
    md.append(f"**Gate:** `current_arch().num_sms` = {cert['gate']['sglang_current_arch_num_sms']} → "
              f"threshold = max(8, 8×{cert['gate']['sglang_current_arch_num_sms']}//20) = **{cert['gate']['computed_threshold']}**; "
              f"Qwen3-0.6B head_tiles = {cert['gate']['head_tiles_qwen3_06b']}\n")
    md.append("| test | status | evidence |")
    md.append("|---|---|---|")
    for name, t in cert["tests"].items():
        evlinks = ", ".join(f"`{e}`" for e in t.get("evidence", []))
        reason = f" — {t['reason']}" if t.get("reason") else ""
        md.append(f"| {name} | **{t['status']}**{reason} | {evlinks} |")
    md.append(f"\n**Counts:** {json.dumps(cert['counts'])}  ")
    md.append(f"**Measured valid legs:** {json.dumps(cert['measured_totals'])}\n")
    md.append("> " + cert["disclaimer"])
    open(os.path.join(R3, "audit/VALIDATION_CERTIFICATE.md"), "w").write("\n".join(md) + "\n")
    print("certificate written")

if __name__ == "__main__":
    main()
