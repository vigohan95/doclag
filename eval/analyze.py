"""Analysis for the DocLag runs. Reads raw JSONL, writes one JSON with every number the paper uses.

usage: analyze.py --items items.jsonl --raw results/*.jsonl --out summary.json [--split test]
Unit of analysis is the item. An item counts as correct in a condition only if the model chose the truth option
in both option orders (strict). "Misled" means it chose the stale option in both orders.
"""
import argparse, collections, glob, json, math, random
from math import comb


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = 2 * sum(comb(n, i) for i in range(0, k + 1)) / 2**n
    return min(1.0, p)


def wilson(k, n, z=1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def cluster_boot(diffs_by_repo, B=10000, seed=11):
    """diffs_by_repo: repo -> list of per-item paired differences. Resample repos with replacement."""
    rng = random.Random(seed)
    repos = list(diffs_by_repo)
    sums = [(sum(diffs_by_repo[r]), len(diffs_by_repo[r])) for r in repos]
    vals = []
    for _ in range(B):
        s = n = 0
        for _ in repos:
            a, b = sums[rng.randrange(len(repos))]
            s += a
            n += b
        vals.append(s / n if n else 0.0)
    vals.sort()
    return vals[int(0.025 * B)], vals[int(0.975 * B)]


def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: ps[i])
    out = [None] * len(ps)
    m = len(ps)
    run = 0
    for r, i in enumerate(idx):
        run = max(run, min(1.0, (m - r) * ps[i]))
        out[i] = run
    return out


def paired(a, b, ids, repo_of):
    """a,b: dict id->bool. returns stats for b minus a"""
    both = [i for i in ids if i in a and i in b]
    bb = sum(1 for i in both if a[i] and not b[i])  # lost going a -> b
    cc = sum(1 for i in both if b[i] and not a[i])  # gained going a -> b
    by = collections.defaultdict(list)
    for i in both:
        by[repo_of[i]].append(int(b[i]) - int(a[i]))
    lo, hi = cluster_boot(by) if both else (None, None)
    return {
        "n": len(both),
        "a_rate": sum(a[i] for i in both) / len(both) if both else None,
        "b_rate": sum(b[i] for i in both) / len(both) if both else None,
        "a_to_b_lost": bb,
        "a_to_b_gained": cc,
        "diff": (cc - bb) / len(both) if both else None,
        "cluster_ci95": [lo, hi],
        "mcnemar_p": mcnemar_exact(bb, cc),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--raw", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="")
    a = ap.parse_args()
    items = {}
    for l in open(a.items, encoding="utf-8"):
        d = json.loads(l)
        if a.split and d.get("split") != a.split:
            continue
        items[d["id"]] = d
    repo_of = {i: d["repo"] for i, d in items.items()}
    rows = collections.defaultdict(list)
    files = []
    for pat in a.raw:
        files += glob.glob(pat)
    for f in files:
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if r["id"] in items and not r.get("error"):
                rows[r["model"]].append(r)
    out = {"n_items": len(items), "n_repos": len(set(repo_of.values())), "files": sorted(files), "models": {}}
    for model, rs in rows.items():
        res = {}
        mc = collections.defaultdict(dict)  # (cond,think) -> id -> {order: choice}
        for r in rs:
            if r["task"] == "mcq":
                mc[(r["cond"], r["think"])].setdefault(r["id"], {})[r["order"]] = r.get("choice")
        strict, misled, table = {}, {}, {}
        for (c, th), d in mc.items():
            name = c + ("+think" if th else "")
            full = {i: v for i, v in d.items() if len(v) == 2} or d
            strict[name] = {i: all(x == "truth" for x in v.values()) for i, v in full.items()}
            misled[name] = {i: all(x == "stale" for x in v.values()) for i, v in full.items()}
            n = len(full)
            cnt = collections.Counter(x for v in full.values() for x in v.values())
            tot = sum(cnt.values())
            k = sum(strict[name].values())
            km = sum(misled[name].values())
            table[name] = {
                "n": n,
                "strict_correct": k,
                "strict_rate": k / n,
                "wilson95": wilson(k, n),
                "both_stale": km,
                "both_stale_rate": km / n,
                "choice_share": {x: cnt[x] / tot for x in ("truth", "stale", "distractor", "cant", None)},
                "order_flip_rate": sum(1 for v in full.values() if len(set(v.values())) > 1) / n,
            }
        res["mcq"] = table
        ids = list(items)
        comps = {}
        for nm, x, y in [("FC_vs_SC", "FC", "SC"), ("C_vs_SC", "C", "SC"), ("SC_vs_SCR", "SC", "SCR"), ("C_vs_FC", "C", "FC"), ("SC_vs_CS", "SC", "CS"), ("FC_vs_FCR", "FC", "FCR"), ("FCL_vs_SCL", "FCL", "SCL"), ("CL_vs_SCL", "CL", "SCL"), ("SC_vs_SCthink", "SC", "SC+think")]:
            if x in strict and y in strict:
                comps[nm] = paired(strict[x], strict[y], ids, repo_of)
        pri = [k for k in ("FC_vs_SC", "C_vs_SC", "SC_vs_SCR") if k in comps]
        if pri:
            for k, p in zip(pri, holm([comps[k]["mcnemar_p"] for k in pri])):
                comps[k]["holm_p"] = p
        if "SC" in misled and "FC" in misled:
            comps["misled_FC_to_SC"] = paired(misled["FC"], misled["SC"], ids, repo_of)
        res["paired"] = comps
        # decomposition: what a passage does to items the model can or cannot read from code alone
        if all(k in strict for k in ("C", "SC", "FC")):
            common = [i for i in ids if i in strict["C"] and i in strict["SC"] and i in strict["FC"]]
            solved = [i for i in common if strict["C"][i]]
            unsolved = [i for i in common if not strict["C"][i]]
            res["decomposition"] = {
                "n": len(common),
                "code_solved": len(solved),
                "override_to_wrong": sum(1 for i in solved if not strict["SC"][i]),
                "override_to_stale": sum(1 for i in solved if misled["SC"].get(i)),
                "override_rate": sum(1 for i in solved if not strict["SC"][i]) / len(solved) if solved else None,
                "override_stale_rate": sum(1 for i in solved if misled["SC"].get(i)) / len(solved) if solved else None,
                "code_unsolved": len(unsolved),
                "rescued_by_fixed_doc": sum(1 for i in unsolved if strict["FC"][i]),
                "rescue_rate": sum(1 for i in unsolved if strict["FC"][i]) / len(unsolved) if unsolved else None,
                "stale_on_unsolved": sum(1 for i in unsolved if misled["SC"].get(i)),
            }

            # break-even staleness: share p of stale claims at which docs+code equals code alone
            def be(sample):
                n = len(sample)
                c = sum(strict["C"][i] for i in sample) / n
                f = sum(strict["FC"][i] for i in sample) / n
                s = sum(strict["SC"][i] for i in sample) / n
                return (f - c) / (f - s) if f > s else None

            byrepo = collections.defaultdict(list)
            for i in common:
                byrepo[repo_of[i]].append(i)
            rng = random.Random(23)
            repos = list(byrepo)
            vals = []
            for _ in range(4000):
                smp = []
                for _ in repos:
                    smp += byrepo[repos[rng.randrange(len(repos))]]
                v = be(smp)
                if v is not None:
                    vals.append(v)
            vals.sort()
            res["break_even"] = {
                "p_star": be(common),
                "cluster_ci95": [vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]] if vals else None,
                "boot_valid": len(vals),
            }
        # differential reading: flag a passage when the answer from the passage alone differs from the answer from code alone
        o0 = lambda c: {i: v.get(0) for i, v in mc.get((c, False), {}).items()}
        if ("C", False) in mc and ("S", False) in mc and ("F", False) in mc:
            cc, ss, ff = o0("C"), o0("S"), o0("F")
            both = [i for i in ids if i in cc and i in ss and i in ff]
            tp = sum(1 for i in both if cc[i] != ss[i])
            fp = sum(1 for i in both if cc[i] != ff[i])
            pc = sum(1 for i in both if cc[i] != ss[i] and cc[i] == ff[i])
            res["differential_detect"] = {
                "n_pairs": len(both),
                "recall_on_stale": tp / len(both) if both else None,
                "false_alarm_on_fixed": fp / len(both) if both else None,
                "paired_correct": pc,
                "paired_correct_rate": pc / len(both) if both else None,
                "paired_wilson95": wilson(pc, len(both)),
            }
        # free form
        fr = collections.defaultdict(dict)
        for r in rs:
            if r["task"] == "free" and r.get("truth_hit") is not None:
                fr[r["cond"]][r["id"]] = r
        ft = {}
        for c, d in fr.items():
            n = len(d)
            th = sum(1 for r in d.values() if r["truth_hit"] and not r.get("stale_hit"))
            sh = sum(1 for r in d.values() if r.get("stale_hit") and not r["truth_hit"])
            ft[c] = {"n": n, "truth_only": th, "stale_only": sh, "truth_rate": th / n if n else None, "stale_rate": sh / n if n else None}
        res["free"] = ft
        if "SC" in fr and "FC" in fr:
            f = lambda c: {i: bool(r["truth_hit"] and not r.get("stale_hit")) for i, r in fr[c].items()}
            res["free_FC_vs_SC"] = paired(f("FC"), f("SC"), ids, repo_of)
        # detection
        dv = collections.defaultdict(dict)
        dvt = collections.defaultdict(dict)
        for r in rs:
            if r["task"] == "detect" and not r["think"]:
                dv[r["id"]][r["cond"]] = r.get("verdict")
            if r["task"] == "detect" and r["think"]:
                dvt[r["id"]][r["cond"]] = r.get("verdict")
        pairs = {i: v for i, v in dv.items() if "S" in v and "F" in v}
        if pairs:
            n = len(pairs)
            tp = sum(v["S"] == "YES" for v in pairs.values())
            fp = sum(v["F"] == "YES" for v in pairs.values())
            both = sum(v["S"] == "YES" and v["F"] == "NO" for v in pairs.values())
            res["detect"] = {
                "n_pairs": n,
                "recall_on_stale": tp / n,
                "false_alarm_on_fixed": fp / n,
                "precision": tp / (tp + fp) if tp + fp else None,
                "paired_correct": both,
                "paired_correct_rate": both / n,
                "paired_wilson95": wilson(both, n),
                "stale_yes_fixed_no": sum(v["S"] == "YES" and v["F"] != "YES" for v in pairs.values()),
                "stale_no_fixed_yes": sum(v["S"] != "YES" and v["F"] == "YES" for v in pairs.values()),
            }
            res["detect"]["mcnemar_p"] = mcnemar_exact(res["detect"]["stale_yes_fixed_no"], res["detect"]["stale_no_fixed_yes"])
        pt = {i: v for i, v in dvt.items() if "S" in v and "F" in v}
        if pt:
            n = len(pt)
            res["detect_think"] = {
                "n_pairs": n,
                "recall_on_stale": sum(v["S"] == "YES" for v in pt.values()) / n,
                "false_alarm_on_fixed": sum(v["F"] == "YES" for v in pt.values()) / n,
                "paired_correct": sum(v["S"] == "YES" and v["F"] == "NO" for v in pt.values()),
                "paired_correct_rate": sum(v["S"] == "YES" and v["F"] == "NO" for v in pt.values()) / n,
            }
        # localisation
        lv = collections.defaultdict(dict)
        for r in rs:
            if r["task"] == "locate":
                lv[r["id"]][r["cond"]] = r
        hit = rnd = n = fz = nf = 0
        for i, v in lv.items():
            if "S" in v:
                g = items[i].get("gold_sentences")
                if g:
                    n += 1
                    hit += v["S"].get("pick") in g
                    rnd += len(g) / max(1, v["S"].get("n_sent") or 1)
            if "F" in v:
                nf += 1
                fz += v["F"].get("pick") == 0
        if n:
            res["locate"] = {"n": n, "acc": hit / n, "wilson95": wilson(hit, n), "random_acc": rnd / n, "says_none_on_fixed": fz / nf if nf else None}
        out["models"][model] = res
    json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    for m, r in out["models"].items():
        print(m, {k: round(v["strict_rate"], 3) for k, v in sorted(r["mcq"].items())})
        for k, v in r["paired"].items():
            print("  ", k, v["n"], round(v["diff"], 3), v["a_to_b_lost"], v["a_to_b_gained"], "p=%.3g" % v["mcnemar_p"], [round(x, 3) for x in v["cluster_ci95"]])
        print("  ", r.get("decomposition"))
        print("  ", r.get("break_even"))
        print("  ", r.get("differential_detect"))
        print("  ", r.get("detect"))
        print("  ", r.get("detect_think"))
        print("  ", r.get("locate"))


if __name__ == "__main__":
    main()
