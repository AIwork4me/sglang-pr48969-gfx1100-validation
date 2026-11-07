import json, os, sys
import triton
import triton.runtime.jit as tjit

LOG = os.environ["SGLANG_LAUNCH_SPY_LOG"]
recs = []
orig = tjit.JITFunction.run

def spy(self, *a, **kw):
    try:
        name = getattr(self, "__name__", "?")
    except Exception:
        name = "?"
    if name == "_fwd_grouped_kernel_stage1":
        recs.append({k: v for k, v in kw.items()
                     if k in ("num_warps", "num_stages", "waves_per_eu",
                              "matrix_instr_nonkdim", "kpack")})
        with open(LOG, "a") as f:
            f.write(json.dumps(recs[-1]) + "\n")
    return orig(self, *a, **kw)

tjit.JITFunction.run = spy
if __name__ == "__main__":
    from sglang.launch_server import run_server
    from sglang.srt.plugins import load_plugins
    from sglang.srt.server_args import prepare_server_args
    load_plugins()
    run_server(prepare_server_args(sys.argv[1:]))
