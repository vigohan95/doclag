"""Split cand_pool.jsonl rows not yet sent to triage into triage/new_NNN.txt. Records what was sent in triage/sent.txt."""
import glob, json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(ROOT, "triage")
sent = set(open(os.path.join(T, "sent.txt")).read().split()) if os.path.exists(os.path.join(T, "sent.txt")) else set()
pool = [json.loads(l) for l in open(os.path.join(ROOT, "cand_pool.jsonl"), encoding="utf-8")]
new = [c for c in pool if c["cid"] not in sent]
B = int(sys.argv[1]) if len(sys.argv) > 1 else 250
n0 = len(glob.glob(os.path.join(T, "new_*.txt")))
for i in range(0, len(new), B):
    with open(os.path.join(T, f"new_{n0 + i // B:03d}.txt"), "w", encoding="utf-8") as f:
        for c in new[i : i + B]:
            o = " ".join(x.strip() for x in c["old"])[:300]
            n = " ".join(x.strip() for x in c["new"])[:300]
            f.write(f"## {c['cid']} {c['repo']} {c['path'][-45:]}\nsubject: {c['subject'][:100]}\n- {o}\n+ {n}\n")
with open(os.path.join(T, "sent.txt"), "a") as f:
    f.write("\n".join(c["cid"] for c in new) + "\n")
print("pool", len(pool), "new", len(new), "files", (len(new) + B - 1) // B, "from", n0)
