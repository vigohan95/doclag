"""Stage 1b: deterministic prefilter of raw candidates, then attach stale and fixed passages from the doc at parent and fix.
Writes cand_pool.jsonl and triage batches (compact text) for a model to read."""
import collections, hashlib, json, os, random, re, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
POS = re.compile(
    r"\b(fix|fixes|fixed|correct|corrected|corrects|correction|wrong|incorrect|inaccura\w*|accura\w*|align|aligned|sync|match|matches|update|updated|outdated|stale|"
    r"mismatch|reflect|reflects|actual|actually|misleading|clarify|clarifies|default|defaults|rename|renamed|no longer|deprecated|mention\w*|describe\w*|document\w*)\b",
    re.I,
)
STRONG = re.compile(r"\b(correct|corrected|corrects|correction|wrong|incorrect|inaccura\w*|accura\w*|outdated|stale|mismatch|misleading|actual|actually|match|matches|align|sync|reflect|no longer)\b", re.I)
BADPATH = re.compile(r"(README[._-](ko|ja|zh|cn|ru|fr|de|es|pt|vi|tr|it)|\.(ko|ja|zh|ru|fr|de|es)\.md$|_zh|-zh|zh_|/examples?/|/tests?/|/test/|CLAUDE\.md|SKILL\.md|\.claude/|/skills?/|/prompts?/|/agents?/)", re.I)
BADTXT = re.compile(r"sponsor|thanks to|star history|discord|<img|<td|<a href|shields\.io", re.I)


def run(a, cwd=None):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


def ascii_ok(s):
    return sum(ord(c) < 128 for c in s) >= 0.97 * max(1, len(s))


def passage(lines, a, b, maxup=6, maxdown=6):
    """Expand [a,b) (0-based) to paragraph limits inside the document."""
    i = a
    while i > 0 and a - i < maxup and lines[i - 1].strip() and not lines[i - 1].startswith("#"):
        i -= 1
    j = b
    while j < len(lines) and j - b < maxdown and lines[j].strip() and not lines[j].startswith("#"):
        j += 1
    head = ""
    for k in range(i - 1, -1, -1):
        if re.match(r"#{1,5} ", lines[k]):
            head = lines[k].strip()
            break
    return head, i, j


def attach(c):
    d = os.path.join(ROOT, "clones", c["repo"].replace("/", "__"))
    o = run(["git", "show", f"{c['sha']}^:{c['path']}"], cwd=d)
    n = run(["git", "show", f"{c['sha']}:{c['path']}"], cwd=d)
    if o.returncode or n.returncode:
        return None
    ol = o.stdout.split("\n")
    nl = n.stdout.split("\n")
    os_ = c["old_start"] - 1
    ns = c["new_start"] - 1
    if ol[os_ : os_ + len(c["old"])] != c["old"] or nl[ns : ns + len(c["new"])] != c["new"]:
        return None
    head, i, j = passage(ol, os_, os_ + len(c["old"]))
    up = os_ - i
    down = j - (os_ + len(c["old"]))
    stale = ol[i:j]
    fixed = nl[ns - up : ns + len(c["new"]) + down]
    if stale[:up] != fixed[:up] or (down and stale[-down:] != fixed[-down:]):
        return None
    pre = (head + "\n\n") if head else ""
    c["stale_passage"] = pre + "\n".join(stale)
    c["fixed_passage"] = pre + "\n".join(fixed)
    c["doc_start"] = i + 1
    c["doc_end"] = j
    return c


def main():
    seen = set()
    pool = []
    for l in open(os.path.join(ROOT, "cand_raw.jsonl"), encoding="utf-8"):
        c = json.loads(l)
        o = " ".join(c["old"])
        n = " ".join(c["new"])
        k = (c["repo"], c["sha"], c["path"], c["old_start"])
        if k in seen or not ascii_ok(o + n) or BADPATH.search(c["path"]) or BADTXT.search(o + n):
            continue
        if not POS.search(c["subject"]):
            continue
        if len(n) > 2.2 * len(o) + 60:  # mostly an addition
            continue
        seen.add(k)
        c["strong"] = bool(STRONG.search(c["subject"]))
        c["cid"] = hashlib.sha256("|".join(map(str, k)).encode()).hexdigest()[:10]
        pool.append(c)
    print("after rules", len(pool), "strong", sum(c["strong"] for c in pool), "repos", len({c["repo"] for c in pool}))
    by = collections.defaultdict(list)
    for c in pool:
        by[c["repo"]].append(c)
    rng = random.Random(5)
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    keep = []
    for r, L in by.items():
        L.sort(key=lambda c: (not c["strong"], -c["ts"]))
        keep += L[:cap]
    print("after per-repo cap", len(keep))
    out = []
    for c in keep:
        try:
            a = attach(c)
        except Exception:
            a = None
        if a:
            out.append(a)
    print("passages attached", len(out))
    rng.shuffle(out)
    with open(os.path.join(ROOT, "cand_pool.jsonl"), "w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    os.makedirs(os.path.join(ROOT, "triage"), exist_ok=True)
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    for bi in range(0, len(out), B):
        with open(os.path.join(ROOT, "triage", f"batch_{bi//B:03d}.txt"), "w", encoding="utf-8") as f:
            for c in out[bi : bi + B]:
                o = " ".join(x.strip() for x in c["old"])[:320]
                n = " ".join(x.strip() for x in c["new"])[:320]
                f.write(f"## {c['cid']} {c['repo']} {c['path'][-50:]}\nsubject: {c['subject'][:110]}\n- {o}\n+ {n}\n")
    print("batches", (len(out) + B - 1) // B)


main()
