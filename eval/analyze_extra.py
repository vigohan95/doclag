"""Extra analyses: tool-loop results, lexical detection baseline, splits by item attribute, test-retest.
usage: analyze_extra.py --items items_test.jsonl --raw 'results/raw_*.jsonl' --agent 'results/agent_*.jsonl' --out extra.json"""
import argparse, collections, glob, json, re, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import mcnemar_exact, wilson, paired

CUT = 1738368000  # 2025-02-01, first month after the stated January 2025 pre-training cutoff

ap = argparse.ArgumentParser()
ap.add_argument("--items", required=True)
ap.add_argument("--raw", default="")
ap.add_argument("--agent", default="")
ap.add_argument("--retest", default="", help="glob of repeat runs, same format as raw")
ap.add_argument("--out", required=True)
a = ap.parse_args()
items = {}
for l in open(a.items, encoding="utf-8"):
    d = json.loads(l)
    items[d["id"]] = d
repo_of = {i: d["repo"] for i, d in items.items()}
ids = list(items)
out = {"n_items": len(items)}

# lexical detection baseline: flag the passage if it names a code-looking token that the code window lacks
TOK = re.compile(r"`([^`\n]{2,60})`")


def lexical(passage, code):
    toks = [t.strip("()") for t in TOK.findall(passage)]
    return any(t and t not in code for t in toks)


tp = sum(lexical(d["stale_passage"], d["code_window"]) for d in items.values())
fp = sum(lexical(d["fixed_passage"], d["code_window"]) for d in items.values())
pc = sum(lexical(d["stale_passage"], d["code_window"]) and not lexical(d["fixed_passage"], d["code_window"]) for d in items.values())
n = len(items)
out["lexical_detect"] = {"n": n, "recall_on_stale": tp / n, "false_alarm_on_fixed": fp / n, "paired_correct": pc, "paired_correct_rate": pc / n}

# splits on the two main conditions
rows = collections.defaultdict(list)
for pat in [a.raw] if a.raw else []:
    for f in glob.glob(pat):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if r["id"] in items and not r.get("error") and r["task"] == "mcq" and not r["think"]:
                rows[r["model"]].append(r)


def strict(rs, cond):
    d = collections.defaultdict(dict)
    for r in rs:
        if r["cond"] == cond:
            d[r["id"]][r["order"]] = r.get("choice")
    return {i: all(x == "truth" for x in v.values()) for i, v in d.items() if len(v) == 2}


keys = {
    "post_cutoff": lambda d: "post" if d["commit_ts"] >= CUT else "pre",
    "kind": lambda d: d["kind"],
    "lang": lambda d: d["lang"],
    "category": lambda d: d["category"],
}
sp = {}
for m, rs in rows.items():
    S = {c: strict(rs, c) for c in ("Q", "C", "SC", "FC")}
    res = {}
    for kn, fn in keys.items():
        g = collections.defaultdict(list)
        for i, d in items.items():
            g[fn(d)].append(i)
        res[kn] = {}
        for k, L in g.items():
            if len(L) < 15:
                continue
            p = paired({i: S["FC"][i] for i in L if i in S["FC"]}, {i: S["SC"][i] for i in L if i in S["SC"]}, L, repo_of)
            res[kn][k] = {"n": len(L), "Q": sum(S["Q"].get(i, False) for i in L) / len(L), "C": sum(S["C"].get(i, False) for i in L) / len(L), "FC": p["a_rate"], "SC": p["b_rate"], "lost": p["a_to_b_lost"], "gained": p["a_to_b_gained"], "p": p["mcnemar_p"]}
    sp[m] = res
out["splits"] = sp

# tool loop
ag = collections.defaultdict(lambda: collections.defaultdict(dict))
if a.agent:
    for f in glob.glob(a.agent):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if r.get("arm") in ("stale", "fixed", "pre-stale", "pre-fixed") and r["id"] in items:
                ag[r["model"]][r["arm"]][r["id"]] = r
res = {}
for m0, arms0 in list(ag.items()):
  for tag, ka, kb in (("plain", "stale", "fixed"), ("preload", "pre-stale", "pre-fixed")):
    m = f"{m0}|{tag}"
    arms = arms0
    s, f = arms.get(ka, {}), arms.get(kb, {})
    both = [i for i in s if i in f]
    if not both:
        continue
    cs = {i: s[i].get("choice") == "truth" for i in both}
    if tag == "preload" and arms.get("stale"):
        base = {i: arms["stale"][i].get("choice") == "truth" for i in both if i in arms["stale"]}
        res[m + "|plain_vs_prestale"] = paired(base, {i: cs[i] for i in base}, list(base), repo_of)
    cf = {i: f[i].get("choice") == "truth" for i in both}
    p = paired(cf, cs, both, repo_of)
    sub = lambda arm, key: sum(1 for i in both if arm[i].get(key)) / len(both) if both else None
    cnt = lambda arm: dict(collections.Counter(str(arm[i].get("choice")) for i in both))
    seen = [i for i in both if s[i].get("saw_passage") and f[i].get("saw_passage")]
    res[m] = {
        "pairs": len(both), "fixed_minus_stale": p, "stale_choices": cnt(s), "fixed_choices": cnt(f),
        "read_code_rate_stale": sub(s, "read_code"), "read_code_rate_fixed": sub(f, "read_code"), "read_doc_rate_stale": sub(s, "read_doc"), "read_doc_rate_fixed": sub(f, "read_doc"),
        "saw_passage_stale": sub(s, "saw_passage"), "saw_passage_fixed": sub(f, "saw_passage"), "mean_turns_stale": sum(s[i]["turns"] for i in both) / len(both) if both else None,
        "no_answer_stale": sum(1 for i in both if s[i].get("choice") is None) / len(both) if both else None,
        "pairs_passage_seen_in_both": len(seen),
        "seen_subset": paired({i: cf[i] for i in seen}, {i: cs[i] for i in seen}, seen, repo_of) if seen else None,
    }
out["agent"] = res

# test-retest on repeated calls
if a.retest:
    base = {}
    for f in glob.glob(a.raw):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            base[(r["model"], r["id"], r["task"], r["cond"], r["order"], r["think"])] = r
    same = tot = 0
    for f in glob.glob(a.retest):
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            k = (r["model"], r["id"], r["task"], r["cond"], r["order"], r["think"])
            if k in base and r["task"] == "mcq":
                tot += 1
                same += base[k].get("choice") == r.get("choice")
    out["retest"] = {"pairs": tot, "same_choice": same, "rate": same / tot if tot else None}
json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k != "splits"}, indent=0, default=str)[:2500])
