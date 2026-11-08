#!/usr/bin/env python3
"""Audit: gate evidence consistency — the recorded core count must match the
environment evidence, the threshold must equal max(8, 8*cc//20), and every
physical launch decision must follow from the arm's rule."""
import json, os, sys

R3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FAILS = []


def ck(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main():
    env = json.load(open(os.path.join(R3, "evidence/environment/gpu_properties.json")))
    cc = env["sglang_current_arch_num_sms"]
    ck("env_core_count_is_48", cc == 48, )
    ck("torch_mpc_equals_sglang_num_sms",
       env["multi_processor_count"] == env["sglang_current_arch_num_sms"])
    thr = max(8, 8 * cc // 20)
    ck("threshold_formula", env["computed_threshold"] == thr, )

    mat = json.load(open(os.path.join(R3, "results/gate_matrix.json")))
    ck("matrix_core_count_matches_env", mat["core_count_runtime"] == cc)
    ck("matrix_threshold_matches_env", mat["new_threshold"] == thr)
    ht = mat["head_tiles_qwen3_06b"]
    ck("head_tiles_is_8", ht == 8)
    for row in mat["rows"]:
        b = row["batch"]
        # main: always hints + warps 4
        if row["main"]:
            ck(f"main_b{b}_hints",
               row["main"]["cdna_hints"] and row["main"]["num_warps"] == 4)
        # old: fixed threshold 8; ht=8 -> b>=1 always drops
        if row["old"]:
            want_drop = not (b * ht < 8)
            ck(f"old_b{b}_{'drop' if want_drop else 'keep'}",
               (not row["old"]["cdna_hints"]) == want_drop and
               row["old"]["num_warps"] == (2 if want_drop else 4))
        # new: scaled threshold
        if row["new"]:
            want_drop = not (b * ht < thr)
            ck(f"new_b{b}_{'drop' if want_drop else 'keep'}",
               (not row["new"]["cdna_hints"]) == want_drop and
               row["new"]["num_warps"] == (2 if want_drop else 4))
    # unit test outcomes
    ck("unit_test_new_arm_all_passed", "7 passed" in mat["unit_tests"]["new_arm"])
    ck("unit_test_old_arm_fails_scaled_test", "failed" in mat["unit_tests"]["old_arm"])
    if FAILS:
        print("GATE AUDIT FAIL:", FAILS)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
