"""Assign dev and test by repository, cap items per repository, and pick the tool-loop subset.
usage: make_splits.py <items_audited.jsonl> <out_dir> [--cap 12]"""
import argparse, collections, hashlib, json, os, random

ap = argparse.ArgumentParser()
ap.add_argument("items")
ap.add_argument("out")
ap.add_argument("--cap", type=int, default=12)
ap.add_argument("--agent-n", type=int, default=150)
a = ap.parse_args()
items = [json.loads(l) for l in open(a.items, encoding="utf-8")]
by = collections.defaultdict(list)
for it in items:
    by[it["repo"]].append(it)
kept = []
for r, L in sorted(by.items()):
    L.sort(key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())
    kept += L[: a.cap]
repos = sorted({i["repo"] for i in kept}, key=lambda r: hashlib.sha256(r.encode()).hexdigest())
dev, n = set(), 0
target = max(30, int(0.1 * len(kept)))
for r in repos:
    if n >= target:
        break
    dev.add(r)
    n += sum(1 for i in kept if i["repo"] == r)
for it in kept:
    it["split"] = "dev" if it["repo"] in dev else "test"
os.makedirs(a.out, exist_ok=True)
for name, sel in (("items_all.jsonl", kept), ("items_dev.jsonl", [i for i in kept if i["split"] == "dev"]), ("items_test.jsonl", [i for i in kept if i["split"] == "test"])):
    with open(os.path.join(a.out, name), "w", encoding="utf-8") as f:
        for it in sel:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
test = [i for i in kept if i["split"] == "test"]
rng = random.Random(42)
pool = sorted(test, key=lambda x: x["id"])
rng.shuffle(pool)
per = collections.Counter()
agent = []
for it in pool:
    if per[it["repo"]] >= 3 or it["stars"] < 0:
        continue
    per[it["repo"]] += 1
    agent.append(it)
    if len(agent) >= a.agent_n:
        break
with open(os.path.join(a.out, "items_agent.jsonl"), "w", encoding="utf-8") as f:
    for it in agent:
        f.write(json.dumps(it, ensure_ascii=False) + "\n")
print("all", len(kept), "dev", n, "test", len(test), "repos", len(repos), "dev repos", len(dev), "agent", len(agent))
print(collections.Counter(i["lang"] for i in kept).most_common())
print(collections.Counter(i["category"] for i in kept).most_common())
print(collections.Counter(i["kind"] for i in kept).most_common(), collections.Counter(i["verify"] for i in kept).most_common())
print("post-cutoff", sum(1 for i in kept if i["commit_ts"] >= 1738368000), "of", len(kept))
