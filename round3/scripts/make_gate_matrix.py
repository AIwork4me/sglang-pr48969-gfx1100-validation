#!/usr/bin/env python3
"""Build round3/results/gate_matrix.json from the recorded gate evidence:
decision table for every (arm, kernel batch) on the ACTUAL W7900 core count,
plus the physical launch-capture summary."""
import json, os, glob

EV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                  "evidence", "gate")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "results", "gate_matrix.json")

def main():
    gates = {}
    for arm in ("main", "old", "new"):
        d = json.load(open(os.path.join(EV, f"gate_{arm}.json")))
        gates[arm] = d

    cc = gates["new"]["device"]["sglang_num_sms"]
    threshold = gates["new"]["computed_threshold"]["threshold"]
    ht = gates["new"]["qwen3_06b_geometry"]["head_tiles"]

    matrix = {
        "core_count_runtime": cc,
        "torch_multi_processor_count": gates["new"]["device"]["torch_multi_processor_count"],
        "rocminfo_compute_units": 96,
        "new_threshold": threshold,
        "old_threshold": 8,
        "head_tiles_qwen3_06b": ht,
        "rows": [],
        "physical_launch_summary": {},
        "unit_tests": {
            "new_arm": open(os.path.join(EV, "upstream_unit_test_new_arm.txt")).read().strip().splitlines()[-1],
            "old_arm": open(os.path.join(EV, "upstream_unit_test_old_arm.txt")).read().strip().splitlines()[-1],
        },
    }
    for b in (1, 2, 4, 8, 16, 32, 64):
        row = {"batch": b, "programs": b * ht}
        for arm in ("main", "old", "new"):
            recs = gates[arm]["launch_captures"].get(f"qwen_b{b}", [])
            if isinstance(recs, list) and recs:
                r = recs[0]
                row[arm] = {
                    "num_warps": r.get("num_warps"),
                    "cdna_hints": any(k in r for k in ("waves_per_eu", "matrix_instr_nonkdim", "kpack")),
                }
            else:
                row[arm] = None
        matrix["rows"].append(row)
    for arm in ("main", "old", "new"):
        matrix["physical_launch_summary"][arm] = {
            c["name"]: c["ok"] for c in gates[arm]["checks"]}
    json.dump(matrix, open(OUT, "w"), indent=2)
    print(json.dumps(matrix["rows"], indent=2))

if __name__ == "__main__":
    main()
