"""Stage 2b: for triaged candidates, pre-search the code at the parent commit and write batch card files that a writer can read in one go.
usage: cards.py <batch_size>   reads cand_triaged.jsonl, writes cards/card_NNN.txt"""
import collections, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from ctx import CODE_GLOBS, CODE_EXT, clone_dir, run

NOISE = set("the a an and or to of in on for is are be with by this that it default true false none null not can may must should only always never before after".split())


def missing_fetch(d, rev):
    r = run(["git", "ls-tree", "-r", rev], cwd=d)
    oids = []
    for l in r.stdout.split("\n"):
        m = re.match(r"\d+ blob ([0-9a-f]{40})\t(.*)", l)
        if m and m[2].lower().endswith(CODE_EXT):
            oids.append(m[1])
    if not oids:
        return
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1")
    p = subprocess.run(["git", "cat-file", "--batch-check"], cwd=d, input="\n".join(oids) + "\n", capture_output=True, text=True, env=env, timeout=300)
    miss = [l.split()[0] for l in p.stdout.split("\n") if l.endswith(" missing")]
    for i in range(0, len(miss), 3000):
        run(["git", "-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none", "--stdin"],
            cwd=d, inp="\n".join(miss[i:i + 3000]) + "\n", timeout=900)


def terms(c):
    out = []
    for t in c["fact_new"] + c["fact_old"] + c["new_only"] + c["old_only"]:
        t = t.strip("`.,;:()'\"[]")
        t = re.sub(r"\(\)$", "", t)
        if len(t) >= 3 and t.lower() not in NOISE and not re.fullmatch(r"\d{1,2}", t) and t not in out:
            out.append(t)
    return out[:4]


def card(c):
    d = clone_dir(c["repo"])
    par = run(["git", "rev-parse", c["sha"] + "^"], cwd=d).stdout.strip()
    if not par:
        return None
    missing_fetch(d, par)
    hits = []
    seen = set()
    for t in terms(c):
        r = run(["git", "grep", "-n", "-I", "-F", "-e", t, par, "--"] + CODE_GLOBS, cwd=d, timeout=120)
        L = [x.replace(par + ":", "", 1) for x in r.stdout.split("\n") if x]
        L = [x for x in L if not re.search(r"(^|/)(tests?|__tests__|fixtures|dist|build|vendor|node_modules|lock|package-lock)", x.split(":")[0])] or L
        hits.append((t, len(L), [x[:150] for x in L[:4]]))
        for x in L[:2]:
            f, n = x.split(":")[0], int(x.split(":")[1])
            if (f, n // 25) not in seen and len(seen) < 3:
                seen.add((f, n // 25))
    snips = []
    for f, b in seen:
        s = run(["git", "show", f"{par}:{f}"], cwd=d).stdout.split("\n")
        n = b * 25 + 12
        lo, hi = max(1, n - 18), min(len(s), n + 18)
        snips.append(f"[{f}:{lo}-{hi}]\n" + "\n".join(f"{i}: {s[i-1][:130]}" for i in range(lo, hi + 1)))
    txt = [f"=== {c['cid']} | {c['repo']} ({c['lang']}, {c['kind']}) | doc {c['path']}", f"subject: {c['subject'][:140]}", "--- stale passage", c["stale_passage"][:1400], "--- fixed passage", c["fixed_passage"][:1600], "--- term hits"]
    for t, n, L in hits:
        txt.append(f"{t!r}: {n} hits; " + " || ".join(L[:3]))
    txt.append("--- code snippets")
    txt += snips
    return "\n".join(txt) + "\n"


def main():
    one = os.path.join(ROOT, "cards_one")
    os.makedirs(one, exist_ok=True)
    C = [json.loads(l) for l in open(os.path.join(ROOT, "cand_triaged.jsonl"), encoding="utf-8")]
    C = [c for c in C if not os.path.exists(os.path.join(one, c["cid"] + ".txt"))]
    by = collections.defaultdict(list)
    for c in C:
        by[c["repo"]].append(c)
    print("todo", len(C), "repos", len(by), flush=True)

    def one_repo(L):
        for c in L:
            try:
                x = card(c)
            except Exception as e:
                x = None
                print("fail", c["cid"], c["repo"], repr(e)[:120], flush=True)
            open(os.path.join(one, c["cid"] + ".txt"), "w", encoding="utf-8").write(x or "")

    with ThreadPoolExecutor(12) as ex:
        list(ex.map(one_repo, sorted(by.values(), key=len)))
    print("done", flush=True)


main()
