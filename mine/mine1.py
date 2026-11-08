"""Stage 1: find doc-only (or comment/docstring-only candidate) commits with small factual edits.
No LLM. Blobless shallow clones; appends to a candidates jsonl."""
import subprocess, re, json, sys, os, difflib, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.abspath(__file__))
CL = os.path.join(ROOT, "clones")
os.makedirs(CL, exist_ok=True)
SINCE = "2024-01-01"
DOC_EXT = (".md", ".mdx", ".rst", ".adoc", ".markdown")
SKIP_PATH = re.compile(
    r"(^|/)(changelog|changes|history|news|release[-_]?notes?|releases?|blog|posts?|i18n|locale|locales|translations?|"
    r"contributors?|authors|code_of_conduct|security|license|licence|funding|roadmap|meeting|rfcs?|adr|notes|whatsnew|"
    r"whats_new|upgrade|migrat\w*|node_modules|vendor|third_party|\.github)(/|\.|$)",
    re.I,
)
LANG_PATH = re.compile(
    r"(^|/)(zh|zh-cn|zh-hans|zh-tw|zh-hant|cn|ja|jp|ko|kr|ru|fr|de|es|pt|pt-br|it|tr|uk|vi|id|ar|fa|pl|bn|hi|nl|he)(/|\.|_|-)",
    re.I,
)
SUBJ_BAD = re.compile(
    r"\b(bump|release|translat\w*|typos?|spelling|spellcheck|grammar|grammatical|broken link|links?|format\w*|lint\w*|"
    r"wording|badge|sponsor\w*|prettier|changelog|merge branch|revert|whitespace|punctuation|capitali[sz]\w*|rephrase|"
    r"reword\w*|markdown|style)\b",
    re.I,
)
CODE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".hpp")
COMMENT_LINE = re.compile(r"^\s*(#|//|/?\*|///|//!|\"\"\"|'''|--)")


def run(a, cwd=None, timeout=300):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


TOK = re.compile(r"`[^`]+`|--?[a-zA-Z][\w-]*|[A-Za-z_][\w.:/-]*\(?\)?|\d[\d.,_]*\w*")
FACT_WORD = set(
    "not never always must required optional default defaults true false none null nil undefined before after only "
    "cannot can may should deprecated removed sync async synchronous asynchronous raises throws returns return ignored "
    "enabled disabled minimum maximum least most first last ascending descending inclusive exclusive milliseconds seconds "
    "minutes hours bytes kb mb".split()
)


def factual(tok):
    t = tok.strip("`.,;:()")
    if not t:
        return False
    if tok.startswith("`"):
        return True
    if re.fullmatch(r"\d[\d.,_]*\w*", t):
        return True
    if t.startswith("-"):
        return len(t) > 2
    if "_" in t or "." in t[1:-1] or tok.endswith("()") or re.search(r"[a-z][A-Z]", t):
        return True
    return t.lower() in FACT_WORD


def is_urlish(s):
    return bool(re.search(r"https?://|\]\(|\.png|\.svg|\.jpg", s))


def pair_hunks(diff):
    out = []
    cur = None
    for ln in diff.split("\n"):
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", ln)
        if m:
            cur = {"o": [], "n": [], "os": int(m[1]), "ns": int(m[3])}
            out.append(cur)
            continue
        if cur is None:
            continue
        if ln.startswith("-") and not ln.startswith("---"):
            cur["o"].append(ln[1:])
        elif ln.startswith("+") and not ln.startswith("+++"):
            cur["n"].append(ln[1:])
    return out


def analyze(o, n):
    os_ = " ".join(x.strip() for x in o)
    ns = " ".join(x.strip() for x in n)
    if not os_ or not ns or len(os_) > 900 or len(ns) > 1200 or len(os_) < 15:
        return None
    r = difflib.SequenceMatcher(None, os_, ns, autojunk=False).ratio()
    if r < 0.45 or r > 0.995:
        return None
    ot = TOK.findall(os_)
    nt = TOK.findall(ns)
    oc = {t.strip("`.,;:").lower() for t in ot}
    nc = {t.strip("`.,;:").lower() for t in nt}
    oo = [t for t in ot if t.strip("`.,;:").lower() not in nc]
    no = [t for t in nt if t.strip("`.,;:").lower() not in oc]
    if not oo and not no:
        return None
    fo = [t for t in oo if factual(t)]
    fn = [t for t in no if factual(t)]
    if not fo and not fn:
        return None
    if len(oo) == len(no) == 1 and difflib.SequenceMatcher(None, oo[0].lower(), no[0].lower()).ratio() > 0.8 and not re.search(r"\d", oo[0] + no[0]) and "`" not in oo[0]:
        return None
    if fo + fn and all(re.fullmatch(r"v?\d+(\.\d+)*[\w.-]*", t.strip("`.,;:")) for t in fo + fn) and re.search(r"version|install|pip|npm|brew|docker|==|@", os_, re.I):
        return None
    if is_urlish(os_) and is_urlish(ns) and not any("`" in t for t in fo + fn):
        return None
    return {"ratio": round(r, 3), "old_only": oo[:12], "new_only": no[:12], "fact_old": fo[:8], "fact_new": fn[:8]}


def process(repo):
    name = repo["full_name"]
    d = os.path.join(CL, name.replace("/", "__"))
    res = []
    try:
        if not os.path.exists(d):
            r = run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", f"--shallow-since={SINCE}", f"https://github.com/{name}.git", d], timeout=900)
            if r.returncode:
                return name, "clone-fail", r.stderr[-200:].replace("\n", " ")
        r = run(["git", "log", "--no-merges", f"--since={SINCE}", "--format=%x01%H%x09%at%x09%s", "--raw", "--no-abbrev", "--no-renames"], cwd=d, timeout=600)
        commits = []
        for blk in r.stdout.split("\x01")[1:]:
            lines = blk.strip("\n").split("\n")
            h, at, s = (lines[0].split("\t", 2) + ["", ""])[:3]
            files = []
            oids = []
            for l in lines[1:]:
                if not l.startswith(":"):
                    continue
                meta, *ps = l.split("\t")
                m = meta.split()
                files.append([m[4]] + ps)
                oids += [m[2], m[3]]
            commits.append((h, int(at or 0), s, files, oids))
        keep = []
        want = set()
        for h, at, s, files, oids in commits:
            if not files or len(files) > 4 or SUBJ_BAD.search(s):
                continue
            paths = [f[-1] for f in files]
            if any(f[0][0] != "M" for f in files):
                continue
            alldoc = all(p.lower().endswith(DOC_EXT) for p in paths)
            allcode = all(p.lower().endswith(CODE_EXT) for p in paths) and re.search(
                r"\b(doc|docs|docstring|docstrings|comment|comments|documentation|jsdoc|javadoc|rustdoc|godoc)\b", s, re.I
            )
            kind = "doc" if alldoc else ("codecomment" if allcode else None)
            if not kind:
                continue
            if kind == "doc" and any(SKIP_PATH.search(p) or LANG_PATH.search(p) for p in paths):
                continue
            keep.append((h, at, s, files, kind))
            want.update(o for o in oids if set(o) != {"0"})
        want = sorted(want)
        for i in range(0, len(want), 2000):
            subprocess.run(["git", "-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none", "--stdin"],
                           cwd=d, input=("\n".join(want[i:i + 2000]) + "\n").encode(), capture_output=True, timeout=900)
        n_doc = 0
        for h, at, s, files, kind in keep:
            n_doc += 1
            r = run(["git", "show", "--format=", "--unified=0", "--no-color", "--no-renames", h], cwd=d, timeout=180)
            if r.returncode:
                continue
            parts = re.split(r"^diff --git ", r.stdout, flags=re.M)[1:]
            for part in parts:
                m = re.search(r"^\+\+\+ b/(.*)$", part, re.M)
                if not m:
                    continue
                p = m[1]
                hunks = pair_hunks(part)
                if len(hunks) > 6:
                    continue
                for hk in hunks:
                    if kind == "codecomment":
                        doc_like = all(COMMENT_LINE.match(x) or not re.search(r"[=(){};]", x) for x in hk["o"] + hk["n"])
                        if not doc_like:
                            continue
                    a = analyze(hk["o"], hk["n"])
                    if a:
                        res.append(
                            dict(repo=name, lang=repo["lang"], lic=repo["lic"], stars=repo["stars"], sha=h, ts=at, subject=s, path=p, kind=kind,
                                 old=hk["o"], new=hk["n"], old_start=hk["os"], new_start=hk["ns"], n_files=len(files), **a)
                        )
        return name, "ok", (len(commits), n_doc, len(res)), res
    except Exception as e:
        return name, "err", repr(e)[:200]


def main():
    ok = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0", "Unlicense", "0BSD", "CC0-1.0"}
    bad = re.compile(r"awesome|tutorial|interview|roadmap|course|leetcode|learn|guide|cheat|free-|public-api|book|example|sample|demo|prompt|system-design|algorithms|study|resources|-list|dotfile|hello", re.I)
    repos = []
    seen = set()
    langs = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    for l in open(os.path.join(ROOT, "repos_raw.tsv"), encoding="utf-8"):
        n, st, lang, lic, size, br = l.rstrip("\n").split("\t")
        if n in seen or lic not in ok or bad.search(n) or int(size) > 1500000 or int(size) < 500:
            continue
        if langs and lang not in langs:
            continue
        seen.add(n)
        repos.append(dict(full_name=n, stars=int(st), lang=lang, lic=lic, size=int(size)))
    logp = os.path.join(ROOT, sys.argv[1] + ".log")
    done = set()
    if os.path.exists(logp):
        done = {l.split("\t")[0] for l in open(logp, encoding="utf-8")}
    repos = [r for r in repos if r["full_name"] not in done]
    repos.sort(key=lambda r: r["size"])
    print(len(repos), "repos to do", flush=True)
    out = open(os.path.join(ROOT, sys.argv[1]), "a", encoding="utf-8")
    log = open(logp, "a", encoding="utf-8")
    t = time.time()
    cnt = 0
    with ThreadPoolExecutor(14) as ex:
        futs = [ex.submit(process, r) for r in repos]
        for fu in as_completed(futs):
            r = fu.result()
            cnt += 1
            log.write("\t".join(map(str, r[:3])) + "\n")
            log.flush()
            if len(r) > 3:
                for c in r[3]:
                    out.write(json.dumps(c, ensure_ascii=False) + "\n")
                out.flush()
            if cnt % 20 == 0:
                print(cnt, int(time.time() - t), flush=True)


main()
