"""Fake deterministic-inference server launcher for determinism.sh mock tests.

Stands in for `python -m sglang.launch_server`. Behavior is driven by env:
  FAKE_MODE=oom          print the canonical OutOfResources(99328>65536) from
                         batch_invariant_ops.py and exit 1
  FAKE_MODE=oom2         a DIFFERENT resource error (Required: 131072)
  FAKE_MODE=crash        an unrelated traceback, exit 3
  FAKE_MODE=ok           start an HTTP server: /health 200; /generate returns
                         deterministic canned text
  FAKE_MODE=mismatch     like ok, but /generate alternates its output text
                         (run-to-run mismatch)
  FAKE_MODE=hang         run forever without opening the port (readiness
                         timeout path)
Also writes its PID/PGID to $FAKE_PIDFILE for cleanup-verification tests.
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = os.environ.get("FAKE_MODE", "ok")

OOM_TEXT = """Traceback (most recent call last):
  File ".../sglang/srt/batch_invariant_ops/batch_invariant_ops.py", line 243, in _matmul_persistent_triton
    matmul_kernel_persistent[grid](
triton.runtime.errors.OutOfResources: out of resource: shared memory, Required: 99328, Hardware limit: 65536
"""


def main() -> int:
    pidfile = os.environ.get("FAKE_PIDFILE")
    if pidfile:
        with open(pidfile, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "pgid": os.getpgid(0)}))
    if MODE == "oom":
        print(OOM_TEXT)
        return 1
    if MODE == "oom2":
        print(OOM_TEXT.replace("99328", "131072").replace("65536", "65536"))
        return 1
    if MODE == "crash":
        print("RuntimeError: something entirely unrelated exploded")
        return 3
    if MODE == "hang":
        while True:
            time.sleep(1)

    port = None
    for i, a in enumerate(sys.argv):
        if a == "--port":
            port = int(sys.argv[i + 1])
    assert port
    state = {"call": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                body = {}
            state["call"] += 1
            if MODE == "mismatch" and state["call"] >= 2:
                text = f"alternating output #{state['call']}"
            else:
                text = "The capital of France is Paris."
            out = json.dumps({"text": text, "meta_info": {"output_ids": [1, 2, 3]}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"[fake] ready mode={MODE} port={port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
