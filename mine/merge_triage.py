"""Collect KEEP cids from triage/out_*.txt into cand_triaged.jsonl (append-only by cid). Prints which are new and writes them to cards_todo.jsonl."""
import glob, json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
keep, drop = set(), set()
for f in glob.glob(os.path.join(ROOT, "triage", "out_*.txt")):
    for l in open(f, encoding="utf-8"):
        m = re.match(r"([0-9a-f]{10})\s+(KEEP|DROP)", l.strip())
        if m:
            (keep if m[2] == "KEEP" else drop).add(m[1])
pool = {c["cid"]: c for c in map(json.loads, open(os.path.join(ROOT, "cand_pool.jsonl"), encoding="utf-8"))}
p = os.path.join(ROOT, "cand_triaged.jsonl")
have = {json.loads(l)["cid"]: json.loads(l) for l in open(p, encoding="utf-8")} if os.path.exists(p) else {}
new = [pool[c] for c in keep if c in pool and c not in have]
with open(p, "a", encoding="utf-8") as f:
    for c in new:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
json.dump({"keep": len(keep), "drop": len(drop), "pool": len(pool), "triaged_total": len(have) + len(new)}, open(os.path.join(ROOT, "funnel_triage.json"), "w"))
print("keep", len(keep), "drop", len(drop), "new", len(new), "total", len(have) + len(new))
