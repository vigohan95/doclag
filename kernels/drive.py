"""Keep two private GPU kernels busy: push the next run when a slot frees up, download output when a run ends.
Status lines go to logs/drive.log. Stops when the queue is empty and all runs are finished."""
import json, os, subprocess, time

K = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(K, "..", "results", "main")
os.makedirs(R, exist_ok=True)
LOG = os.path.join(K, "..", "logs", "drive.log")
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
queue = [
    ("gp-31b", ["gemma4:31b", "--split", "--par", "2", "--eval", "--items items_sub250.jsonl --tasks mcq,free,detect --conds C,SC,FC,SCR --free-conds SC,FC", "--deadline", "40000"]),
    ("gp-mit-12b", ["gemma4:12b", "--par", "3", "--agent", "--items items_agent.jsonl --arms stale,fixed,pre-stale,pre-fixed,pre-stale-rule,pre-fixed-rule,pre-stale-gate,pre-fixed-gate", "--agent-script", "run_agent2.py", "--deadline", "20000"]),
    ("gp-retest", ["gemma4:e4b", "--eval", "--items items_retest40.jsonl --tasks mcq --conds C,SC,FC", "--deadline", "3000"]),
]
active = ["gp-12b", "gp-26b"]
done = {}


def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ", time.gmtime()) + " ".join(map(str, a)) + "\n")


def status(k):
    r = subprocess.run(["kaggle", "kernels", "status", f"hanvigo/{k}"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    t = (r.stdout + r.stderr).strip().split("\n")[-1]
    return t.split("KernelWorkerStatus.")[-1].strip('" ') if "KernelWorkerStatus" in t else "ERR:" + t[:80]


while queue or active:
  try:
    for k in list(active):
        s = status(k)
        if s in ("COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED", "CANCELED"):
            d = os.path.join(R, k)
            os.makedirs(d, exist_ok=True)
            subprocess.run(["kaggle", "kernels", "output", f"hanvigo/{k}", "-p", d], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
            done[k] = s
            active.remove(k)
            log("finished", k, s, sorted(os.listdir(d))[:8])
    while queue and len(active) < 2:
        k, args = queue[0]
        r = subprocess.run(["python", os.path.join(K, "push_run.py"), k] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        log("push", k, (r.stdout + r.stderr)[-160:].replace("\n", " "))
        if "pushed" in r.stdout or "pushed" in r.stderr:
            active.append(k)
            queue.pop(0)
        else:
            break
    log("active", [(k, status(k)) for k in active], "queue", [q[0] for q in queue])
  except Exception as e:
    log("loop error", repr(e)[:200])
  time.sleep(240)
log("ALL DONE", done)
