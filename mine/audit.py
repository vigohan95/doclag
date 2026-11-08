"""Blind solvability audit. prep: write batches holding only question, shuffled options and the code window (no labels, no passages).
collect: read answers, keep items the auditor solved, write items_audited.jsonl and funnel_audit.json."""
import glob, hashlib, json, os, random, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(ROOT, "audit")
os.makedirs(A, exist_ok=True)
CANT = "The material given does not determine the answer"


def opts(it):
    rng = random.Random("audit" + it["id"])
    o = [("truth", it["truth_option"]), ("stale", it["stale_option"]), ("distractor", it["distractor_option"])]
    rng.shuffle(o)
    return o + [("cant", CANT)]


items = [json.loads(l) for l in open(os.path.join(ROOT, "items_all.jsonl"), encoding="utf-8")]
if sys.argv[1] == "prep":
    B = int(sys.argv[2])
    done = set()
    for f in glob.glob(os.path.join(A, "ans_*.txt")):
        done |= {l.split()[0] for l in open(f, encoding="utf-8") if l.strip()}
    n0 = len(glob.glob(os.path.join(A, "batch_*.txt")))
    sent_p = os.path.join(A, "sent.txt")
    sent = set(open(sent_p).read().split()) if os.path.exists(sent_p) else set()
    todo = [it for it in items if it["id"] not in done and it["id"] not in sent]
    for i in range(0, len(todo), B):
        with open(os.path.join(A, f"batch_{n0 + i // B:03d}.txt"), "w", encoding="utf-8") as f:
            for it in todo[i : i + B]:
                body = "\n".join(f"{'ABCD'[k]}) {o[1]}" for k, o in enumerate(opts(it)))
                f.write(f"#### {it['id']} ({it['repo']})\nSource code ({it['code_path']}):\n<<<\n{it['code_window']}\n>>>\nQuestion: {it['question']}\n{body}\n\n")
    with open(sent_p, "a") as f:
        f.write("\n".join(it["id"] for it in todo) + "\n")
    print("items", len(items), "new", len(todo), "batches from", n0)
else:
    ans = {}
    for f in glob.glob(os.path.join(A, "ans_*.txt")):
        for l in open(f, encoding="utf-8"):
            m = re.match(r"([0-9a-f]{10})\s+([ABCD])", l.strip())
            if m:
                ans[m[1]] = m[2]
    res = {"truth": 0, "stale": 0, "distractor": 0, "cant": 0, "missing": 0}
    keep = []
    flagged = []
    for it in items:
        a = ans.get(it["id"])
        if a is None:
            res["missing"] += 1
            continue
        c = opts(it)["ABCD".index(a)][0]
        res[c] += 1
        if c == "truth":
            it["audit"] = "blind-solved"
            keep.append(it)
        else:
            flagged.append((it["id"], c))
    with open(os.path.join(ROOT, "items_audited.jsonl"), "w", encoding="utf-8") as f:
        for it in keep:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    json.dump({"auditor_choices": res, "kept": len(keep), "flagged": flagged}, open(os.path.join(ROOT, "funnel_audit.json"), "w"), indent=1)
    print(res, "kept", len(keep))
