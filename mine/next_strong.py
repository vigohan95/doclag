"""One more triage round: untriaged candidates with a correction-style subject, widest repository spread first."""
import collections, glob, json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
T = os.path.join(ROOT, "triage")
sent = set(open(os.path.join(T, "sent.txt")).read().split())
pool = [json.loads(l) for l in open(os.path.join(ROOT, "cand_pool.jsonl"), encoding="utf-8")]
items = [json.loads(l) for l in open(os.path.join(ROOT, "items_all.jsonl"), encoding="utf-8")]
have = collections.Counter(i["repo"] for i in items)
new = [c for c in pool if c["cid"] not in sent and c["strong"]]
per = collections.Counter()
out = []
new.sort(key=lambda c: (c["lang"] != "Python", have[c["repo"]], -c["stars"]))
for c in new:
    if per[c["repo"]] + have[c["repo"]] >= 8:
        continue
    per[c["repo"]] += 1
    out.append(c)
N = int(sys.argv[1])
out = out[:N]
print("eligible", len(new), "picked", len(out), collections.Counter(c["lang"] for c in out).most_common(), "repos", len({c["repo"] for c in out}))
n0 = len(glob.glob(os.path.join(T, "new_*.txt")))
B = 260
for i in range(0, len(out), B):
    with open(os.path.join(T, f"new_{n0 + i // B:03d}.txt"), "w", encoding="utf-8") as f:
        for c in out[i : i + B]:
            o = " ".join(x.strip() for x in c["old"])[:300]
            n = " ".join(x.strip() for x in c["new"])[:300]
            f.write(f"## {c['cid']} {c['repo']} {c['path'][-45:]}\nsubject: {c['subject'][:100]}\n- {o}\n+ {n}\n")
    print(f"new_{n0 + i // B:03d}.txt")
with open(os.path.join(T, "sent.txt"), "a") as f:
    f.write("\n".join(c["cid"] for c in out) + "\n")
