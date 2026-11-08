"""Collect every number the paper uses into results/final/numbers.json and print a compact digest.
Runs analyze.py logic per model over results/main/*/raw_*.jsonl and the agent files, on the frozen test items."""
import collections, glob, json, os, subprocess, sys

H = os.path.dirname(os.path.abspath(__file__))
B = os.path.join(H, "..")
sys.path.insert(0, H)
from analyze import paired, wilson, mcnemar_exact

items_p = os.path.join(B, "data_v1", "items_test.jsonl")
items = {json.loads(l)["id"]: json.loads(l) for l in open(items_p, encoding="utf-8")}
repo_of = {i: d["repo"] for i, d in items.items()}
out_d = os.path.join(B, "results", "final")
os.makedirs(out_d, exist_ok=True)
raws = sorted(glob.glob(os.path.join(B, "results", "main", "*", "raw_*.jsonl")))
raws = [r for r in raws if "gp-retest" not in r]
subprocess.run([sys.executable, os.path.join(H, "analyze.py"), "--items", items_p, "--raw"] + raws + ["--out", os.path.join(out_d, "summary.json")], capture_output=True)
agents = sorted(glob.glob(os.path.join(B, "results", "main", "*", "agent_*.jsonl")))
subprocess.run([sys.executable, os.path.join(H, "analyze_extra.py"), "--items", items_p, "--raw", os.path.join(B, "results", "main", "gp-[e1-9]*", "raw_*.jsonl"),
                "--agent", os.path.join(B, "results", "main", "gp-[e1-9]*", "agent_*.jsonl"), "--out", os.path.join(out_d, "extra.json")], capture_output=True)
S = json.load(open(os.path.join(out_d, "summary.json")))
E = json.load(open(os.path.join(out_d, "extra.json")))

# agent arms from every agent file (plain, preload, and post-hoc arms)
arms = collections.defaultdict(lambda: collections.defaultdict(dict))
dup = collections.defaultdict(lambda: collections.defaultdict(dict))
# runs of the frozen run_agent.py first; post-hoc runs (gp-mit-*) only add arms that are missing,
# and their repeats of the base arms are kept apart as an agent retest
for f in sorted(agents, key=lambda x: "gp-mit-" in x):
    post = "gp-mit-" in f
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if not (r.get("arm") and r["id"] in items and "choice" in r):
            continue
        if post and r["id"] in arms[r["model"]].get(r["arm"], {}):
            dup[r["model"]][r["arm"]][r["id"]] = r
        else:
            arms[r["model"]][r["arm"]][r["id"]] = r
AGRT = {}
for m, A in dup.items():
    for arm, d in A.items():
        base = arms[m][arm]
        same = sum(1 for i, r in d.items() if base[i]["choice"] == r["choice"])
        acc2 = sum(r["choice"] == "truth" for r in d.values()) / len(d)
        AGRT[f"{m}|{arm}"] = {"n": len(d), "same_choice": same, "rate": same / len(d), "acc_first": sum(base[i]["choice"] == "truth" for i in d) / len(d), "acc_repeat": acc2}
AG = {}
for m, A in arms.items():
    res = {}
    for arm, d in A.items():
        L = list(d.values())
        n = len(L)
        k = sum(x["choice"] == "truth" for x in L)
        res[arm] = {"n": n, "acc": k / n, "wilson95": wilson(k, n), "stale": sum(x["choice"] == "stale" for x in L) / n,
                    "cant": sum(x["choice"] == "cant" for x in L) / n, "none": sum(x["choice"] is None for x in L) / n,
                    "turns": sum(x["turns"] for x in L) / n, "read_evidence_file": sum(bool(x.get("read_code")) for x in L) / n,
                    "read_any_source": sum(bool(x.get("read_src")) for x in L) / n if "read_src" in L[0] else None,
                    "saw_passage": sum(bool(x.get("saw_passage")) for x in L) / n}
    acc = lambda arm: {i: x["choice"] == "truth" for i, x in A.get(arm, {}).items()}
    comps = {}
    for nm, x, y in [("prefixed_vs_prestale", "pre-fixed", "pre-stale"), ("plainstale_vs_prestale", "stale", "pre-stale"), ("plainstale_vs_prefixed", "stale", "pre-fixed"),
                     ("plainfixed_vs_plainstale", "fixed", "stale"), ("prestale_vs_rule", "pre-stale", "pre-stale-rule"), ("prestale_vs_gate", "pre-stale", "pre-stale-gate"),
                     ("prefixed_vs_rule", "pre-fixed", "pre-fixed-rule"), ("prefixed_vs_gate", "pre-fixed", "pre-fixed-gate")]:
        a, b = acc(x), acc(y)
        ids = [i for i in a if i in b]
        if ids:
            comps[nm] = paired(a, b, ids, repo_of)
    # among pre-stale episodes that read the evidence file
    ps = A.get("pre-stale", {})
    pf = A.get("pre-fixed", {})
    both = [i for i in ps if i in pf and ps[i].get("read_code") and pf[i].get("read_code")]
    if both:
        comps["prefixed_vs_prestale_when_both_read_evidence"] = paired({i: pf[i]["choice"] == "truth" for i in both}, {i: ps[i]["choice"] == "truth" for i in both}, both, repo_of)
    if all(k in res for k in ("stale", "pre-stale", "pre-fixed")):
        c, s, f = res["stale"]["acc"], res["pre-stale"]["acc"], res["pre-fixed"]["acc"]
        res["_break_even_share_stale"] = (f - c) / (f - s) if f > s else None
    AG[m] = {"arms": res, "paired": comps}

# retest
rt = {}
base = {}
for f in raws:
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if r["task"] == "mcq" and not r["think"]:
            base[(r["model"], r["id"], r["cond"], r["order"])] = r.get("choice")
for f in glob.glob(os.path.join(B, "results", "main", "gp-retest", "raw_*.jsonl")):
    same = tot = 0
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        k = (r["model"], r["id"], r["cond"], r["order"])
        if k in base:
            tot += 1
            same += base[k] == r.get("choice")
    rt[os.path.basename(f)] = {"pairs": tot, "same": same, "rate": same / tot if tot else None}

# parse failures and prompt sizes
pf = {}
for f in raws:
    c = collections.Counter()
    mx = 0
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        c["calls"] += 1
        c["errors"] += bool(r.get("error"))
        c["mcq_unparsed"] += r["task"] == "mcq" and r.get("letter") is None
        c["truncated"] += r.get("done_reason") == "length"
        mx = max(mx, r.get("prompt_tokens") or 0)
    pf[os.path.basename(f)] = dict(c, max_prompt_tokens=mx)

N = {"items": S["n_items"], "repos": S["n_repos"], "models": S["models"], "agent": AG, "agent_retest": AGRT, "extra": E, "retest": rt, "calls": pf}
json.dump(N, open(os.path.join(out_d, "numbers.json"), "w", encoding="utf-8"), indent=1, default=str)
for m, r in S["models"].items():
    t = r["mcq"]
    print(m, " ".join(f"{k}={t[k]['strict_rate']:.3f}" for k in sorted(t)))
    for k in ("FC_vs_SC", "C_vs_SC", "SC_vs_SCR"):
        if k in r["paired"]:
            v = r["paired"][k]
            print("   ", k, f"{v['diff']:+.3f}", v["a_to_b_lost"], v["a_to_b_gained"], "p=%.2g" % v["mcnemar_p"], "holm=%.2g" % v.get("holm_p", -1))
    if "free_FC_vs_SC" in r:
        v = r["free_FC_vs_SC"]
        print("    free", f"{v['a_rate']:.3f}->{v['b_rate']:.3f}", v["a_to_b_lost"], v["a_to_b_gained"], "p=%.2g" % v["mcnemar_p"])
    for k in ("detect", "detect_think", "differential_detect"):
        if k in r:
            print("   ", k, {a: round(b, 3) for a, b in r[k].items() if isinstance(b, float)})
for m, a in AG.items():
    print(m, {k: round(v["acc"], 3) for k, v in a["arms"].items() if not k.startswith("_")}, "be", a["arms"].get("_break_even_share_stale"))
    for k, v in a["paired"].items():
        print("   ", k, v["n"], f"{v['diff']:+.3f}", v["a_to_b_lost"], v["a_to_b_gained"], "p=%.2g" % v["mcnemar_p"])
print("retest", rt)
print("agent retest", AGRT)
print("calls", pf)
