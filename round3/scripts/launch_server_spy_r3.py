import json, os, sys
import triton.runtime.jit as tjit

LOG = os.environ["SGLANG_LAUNCH_SPY_LOG"]
recs = 0
orig = tjit.JITFunction.run

def spy(self, *a, **kw):
    global recs
    try:
        name = getattr(self, "__name__", "?")
    except Exception:
        name = "?"
    if name == "_fwd_grouped_kernel_stage1":
        rec = {k: v for k, v in kw.items()
               if k in ("num_warps", "num_stages", "waves_per_eu",
                        "matrix_instr_nonkdim", "kpack")}
        grid = kw.get("grid")
        try:
            rec["grid"] = [int(x) for x in (grid() if callable(grid) else grid)]
        except Exception:
            rec["grid"] = str(grid)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        recs += 1
    return orig(self, *a, **kw)

tjit.JITFunction.run = spy
if __name__ == "__main__":
    from sglang.launch_server import run_server
    from sglang.srt.plugins import load_plugins
    from sglang.srt.server_args import prepare_server_args
    load_plugins()
    run_server(prepare_server_args(sys.argv[1:]))
