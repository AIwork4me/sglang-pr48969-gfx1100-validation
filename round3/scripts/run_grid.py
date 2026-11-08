#!/usr/bin/env python3
"""Round 3 campaign orchestrator: generates the leg schedule and executes each
leg via run_leg.sh (fresh server per leg). Fail-closed per leg with one retry;
failed legs are recorded and skipped (the analyzer/audit count valid runs).

Schedule (all fresh-server legs, warmup before every measured run):
  P0  c=1,2,4,8 : Main/New x3 ABBA cycles (orientation alternating ABBA/BAAB)
                       interleaved with Old/New x2 ABBA cycles
  P0+ sustained c=1, 32 sequential prompts: Main/New x2 + Old/New x1 cycles
  P1  c=16,32,64: Main/New x1 ABBA
  P1b c=1 memfrac 0.30 auto KV: 6-leg rotations x2 (all three arms symmetric)
"""
import json, os, subprocess, sys, time

CAMP = os.environ.get("SGLANG_VALIDATION_ROOT",
                      os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
WORK = os.environ.get("SGLANG_VALIDATION_WORK", "/workspace/round3-work")
EV = os.path.join(CAMP, "round3", "evidence", "performance")
IL, OL, RR = 1024, 256, 1
MAXTOK = 100000

def legs_p0(c):
    legs = []
    # cycle 1 MN ABBA
    legs += [("main", 1), ("new", 1), ("new", 2), ("main", 2)]
    # cycle 1 ON ABBA
    legs += [("old", 1), ("new", 3), ("new", 4), ("old", 2)]
    # cycle 2 MN BAAB
    legs += [("new", 5), ("main", 3), ("main", 4), ("new", 6)]
    # cycle 2 ON BAAB
    legs += [("new", 7), ("old", 3), ("old", 4), ("new", 8)]
    # cycle 3 MN ABBA
    legs += [("main", 5), ("new", 9), ("new", 10), ("main", 6)]
    return legs

def legs_sustained():
    legs = []
    legs += [("main", 1), ("new", 1), ("new", 2), ("main", 2)]   # MN ABBA
    legs += [("old", 1), ("new", 3), ("new", 4), ("old", 2)]     # ON ABBA
    legs += [("new", 5), ("main", 3), ("main", 4), ("new", 6)]   # MN BAAB
    return legs

def legs_p1(c):
    return [("main", 1), ("new", 1), ("new", 2), ("main", 2)]

def legs_memfrac():
    s1 = [("main", 1), ("new", 1), ("old", 1), ("old", 2), ("new", 2), ("main", 2)]
    s2 = [("new", 3), ("main", 3), ("old", 3), ("old", 4), ("main", 4), ("new", 4)]
    return s1 + s2

CELLS = []
for c in (1, 2, 4, 8):
    CELLS.append({"tag": f"c{c}", "conc": c, "nprompts": c, "memfrac": "0.75",
                  "maxtok": MAXTOK, "legs": legs_p0(c)})
CELLS.append({"tag": "sustained_c1", "conc": 1, "nprompts": 32, "memfrac": "0.75",
              "maxtok": MAXTOK, "legs": legs_sustained()})
for c in (16, 32, 64):
    CELLS.append({"tag": f"c{c}", "conc": c, "nprompts": c, "memfrac": "0.75",
                  "maxtok": MAXTOK, "legs": legs_p1(c)})
CELLS.append({"tag": "memfrac030_c1", "conc": 1, "nprompts": 1, "memfrac": "0.30",
              "maxtok": 0, "legs": legs_memfrac()})

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    order_log = os.path.join(EV, "order.jsonl")
    os.makedirs(EV, exist_ok=True)
    with open(order_log, "a") as order:
        for cell in CELLS:
            if only and cell["tag"] != only:
                continue
            cell_dir = os.path.join(EV, cell["tag"])
            os.makedirs(cell_dir, exist_ok=True)
            for arm, runno in cell["legs"]:
                sfx = f"{arm}_r{runno}"
                bench = os.path.join(cell_dir, f"bench_{sfx}.json")
                if os.path.exists(bench) and os.path.getsize(bench) > 0:
                    print(f"[skip existing] {cell['tag']}/{sfx}", flush=True)
                    order.write(json.dumps({"cell": cell["tag"], "arm": arm, "run": runno,
                                            "status": "skipped_existing"}) + "\n")
                    continue
                rec = {"cell": cell["tag"], "arm": arm, "run": runno,
                       "conc": cell["conc"], "nprompts": cell["nprompts"],
                       "memfrac": cell["memfrac"], "maxtok": cell["maxtok"],
                       "il": IL, "ol": OL, "rr": RR,
                       "utc_start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                ok = False
                for attempt in (1, 2):
                    print(f"[leg] {cell['tag']}/{sfx} attempt {attempt} {rec['utc_start']}", flush=True)
                    r = subprocess.run(
                        ["bash", os.path.join(CAMP, "round3/scripts/run_leg.sh"),
                         cell_dir, arm, str(runno), str(cell["conc"]), str(IL), str(OL),
                         str(RR), cell["memfrac"], str(cell["maxtok"]), str(cell["nprompts"]), "plain"],
                        cwd=CAMP)
                    if r.returncode == 0:
                        ok = True
                        break
                    time.sleep(20)
                rec["status"] = "ok" if ok else "FAILED"
                rec["utc_end"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                order.write(json.dumps(rec) + "\n")
                order.flush()
    print("GRID DONE")

if __name__ == "__main__":
    main()
