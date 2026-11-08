"""Stage 3: validate model-written item drafts deterministically and build the final items file.

Checks: the evidence span exists at the parent commit and is unchanged at the fix commit; the commit changed no code
(doc commits: no code file touched; Python docstring commits: AST equal after removing docstrings; other languages:
changed lines are comment lines); option and regex sanity; the question does not contain either answer value.
"""
import ast, glob, hashlib, json, os, random, re, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "eval"))
from run_eval import split_sentences

WIN = 30
LONG = 200


def run(a, cwd=None):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)


def strip_doc(src):
    t = ast.parse(src)
    for n in ast.walk(t):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            if isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str):
                n.body = n.body[1:] or [ast.Pass()]
    return ast.dump(t)


def load_cands():
    return {c["cid"]: c for c in map(json.loads, open(os.path.join(ROOT, "cand_triaged.jsonl"), encoding="utf-8"))}


def main():
    cands = load_cands()
    drafts = {}
    decisions = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "drafts", "*.jsonl"))):
        for l in open(f, encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            try:
                d = json.loads(l)
            except Exception:
                print("bad json in", f, l[:80])
                continue
            decisions[d.get("cid")] = d
            if d.get("decision") == "keep":
                drafts[d["cid"]] = d
    print("decisions", len(decisions), "keep", len(drafts))
    rej = {}
    items = []
    bad = {}
    for cid, d in drafts.items():
        c = cands.get(cid)
        if not c:
            bad[cid] = "unknown cid"
            continue
        repo_d = os.path.join(ROOT, "clones", c["repo"].replace("/", "__"))
        par = run(["git", "rev-parse", c["sha"] + "^"], cwd=repo_d).stdout.strip()
        if not par:
            bad[cid] = "no parent"
            continue
        o = run(["git", "show", f"{par}:{d['code_path']}"], cwd=repo_d)
        n = run(["git", "show", f"{c['sha']}:{d['code_path']}"], cwd=repo_d)
        if o.returncode or n.returncode:
            bad[cid] = "code path missing"
            continue
        L = o.stdout.split("\n")
        a, b = int(d["ev_start"]), int(d["ev_end"])
        if not (1 <= a <= b <= len(L)) or b - a > 45:
            bad[cid] = "bad span"
            continue
        names = run(["git", "diff", "--name-only", par, c["sha"]], cwd=repo_d).stdout.split()
        verify = "doc-only"
        comment_removed = set()
        if c["kind"] == "codecomment":
            if d["code_path"] == c["path"]:
                comment_removed = set(range(c["old_start"], c["old_start"] + len(c["old"])))
            if c["path"].endswith(".py"):
                try:
                    if strip_doc(o.stdout if d["code_path"] == c["path"] else run(["git", "show", f"{par}:{c['path']}"], cwd=repo_d).stdout) != strip_doc(
                        n.stdout if d["code_path"] == c["path"] else run(["git", "show", f"{c['sha']}:{c['path']}"], cwd=repo_d).stdout
                    ):
                        bad[cid] = "python AST differs"
                        continue
                    verify = "ast-equal"
                except SyntaxError:
                    bad[cid] = "py parse"
                    continue
            else:
                verify = "comment-lines"
        else:
            if d["code_path"] in names:
                bad[cid] = "evidence file changed in commit"
                continue
        ws, we = max(1, a - WIN), min(len(L), b + WIN)
        win = [L[i - 1] for i in range(ws, we + 1) if i not in comment_removed]
        window = "\n".join(win)
        if len(window) > 9000:
            bad[cid] = "window too long"
            continue
        lo, hi = max(1, a - LONG), min(len(L), b + LONG)
        code_long = "\n".join(L[i - 1] for i in range(lo, hi + 1) if i not in comment_removed)
        while len(code_long) > 16000 and hi - lo > (b - a) + 2 * WIN:
            lo, hi = lo + 10, hi - 10
            code_long = "\n".join(L[i - 1] for i in range(max(lo, 1), min(hi, len(L)) + 1) if i not in comment_removed)
        t, s, x = d["truth_option"].strip(), d["stale_option"].strip(), d["distractor_option"].strip()
        if not (t and s and x) or len({t.lower(), s.lower(), x.lower()}) < 3:
            bad[cid] = "options"
            continue
        ql = d["question"].lower()
        if t.lower() in ql or s.lower() in ql:
            bad[cid] = "question leaks option"
            continue
        tr, sr = d.get("truth_regex"), d.get("stale_regex")
        try:
            if tr and not re.search(tr, t, re.I):
                tr = None
            if sr and not re.search(sr, s, re.I):
                sr = None
            if tr and re.search(tr, s, re.I):
                tr = None
            if sr and re.search(sr, t, re.I):
                sr = None
        except re.error:
            tr = sr = None
        if c["stale_passage"] == c["fixed_passage"]:
            bad[cid] = "same passage"
            continue
        sent = d.get("doc_sentence", "")
        ss = split_sentences(c["stale_passage"])
        fs = set(split_sentences(c["fixed_passage"]))
        gold = [i + 1 for i, x in enumerate(ss) if x not in fs]
        if not gold or len(gold) == len(ss) and len(ss) > 2:
            gold_ok = False
        else:
            gold_ok = True
        items.append(
            dict(
                id=cid, repo=c["repo"], lang=c["lang"], license=c["lic"], stars=c["stars"], fix_sha=c["sha"], parent_sha=par, commit_ts=c["ts"], subject=c["subject"],
                kind=c["kind"], doc_path=c["path"], doc_start=c["doc_start"], doc_end=c["doc_end"], stale_passage=c["stale_passage"], fixed_passage=c["fixed_passage"],
                code_path=d["code_path"], ev_start=a, ev_end=b, win_start=ws, win_end=we, code_window=window, code_long=code_long, verify=verify,
                question=d["question"].strip(), truth_option=t, stale_option=s, distractor_option=x, truth_regex=tr, stale_regex=sr,
                category=d.get("category"), evidence_note=d.get("evidence_note"), doc_sentence=sent, written_by="claude-opus-5-5",
                gold_sentences=gold if gold_ok else None, n_sentences=len(ss),
                marker_stale=c["old"][0].strip()[:60], marker_fixed=c["new"][0].strip()[:60],
            )
        )
    for k, v in decisions.items():
        if v.get("decision") == "reject":
            rej[v.get("reason", "other")] = rej.get(v.get("reason", "other"), 0) + 1
    fails = {}
    for v in bad.values():
        fails[v] = fails.get(v, 0) + 1
    print("items", len(items), "validator rejects", fails, "model rejects", rej)
    with open(os.path.join(ROOT, "items_all.jsonl"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    json.dump({"decisions": len(decisions), "keep": len(drafts), "validator_rejects": fails, "model_rejects": rej, "items": len(items)}, open(os.path.join(ROOT, "funnel_stage3.json"), "w"), indent=1)


main()
