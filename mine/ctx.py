"""Read-only helper for writing and checking items. Works at the parent commit of a candidate.

  python ctx.py card  <cid>                 candidate card: subject, stale and fixed passage, changed tokens
  python ctx.py grep  <cid> <regex> [glob]  git grep at the parent commit (code files), max 40 lines
  python ctx.py show  <cid> <path> <a> <b>  print lines a..b of path at the parent commit, with line numbers
  python ctx.py files <cid> <substring>     list paths at the parent commit containing substring
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(ROOT, "cand_triaged.jsonl")
CODE_GLOBS = ["*.py", "*.js", "*.mjs", "*.cjs", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs", "*.java", "*.kt", "*.rb", "*.php", "*.c", "*.h", "*.cc", "*.cpp", "*.hpp", "*.toml", "*.yaml", "*.yml", "*.json"]
CODE_EXT = tuple(g[1:] for g in CODE_GLOBS)


def run(a, cwd=None, inp=None, timeout=600):
    # bytes in, so Windows text mode does not turn the newlines of a --stdin list into CRLF
    r = subprocess.run(a, cwd=cwd, input=inp.encode() if inp is not None else None, capture_output=True, timeout=timeout)
    r.stdout = r.stdout.decode("utf-8", "replace")
    r.stderr = r.stderr.decode("utf-8", "replace")
    return r


def clone_dir(repo):
    return os.path.join(ROOT, "clones", repo.replace("/", "__"))


def load():
    return {c["cid"]: c for c in map(json.loads, open(CAND, encoding="utf-8"))}


def ensure_blobs(d, rev):
    """Fetch every code blob of rev in one request, once per (repo, rev)."""
    marker = os.path.join(d, f".blobs-{rev[:12]}")
    if os.path.exists(marker) or os.path.exists(os.path.join(d, ".git", f"blobs-{rev[:12]}")):
        return
    r = run(["git", "ls-tree", "-r", rev], cwd=d)
    want = []
    for l in r.stdout.split("\n"):
        m = re.match(r"\d+ blob ([0-9a-f]{40})\t(.*)", l)
        if m and m[2].lower().endswith(CODE_EXT + (".md", ".mdx", ".rst")):
            want.append(m[1])
    for i in range(0, len(want), 3000):
        run(["git", "-c", "fetch.negotiationAlgorithm=noop", "fetch", "origin", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no", "--filter=blob:none", "--stdin"],
            cwd=d, inp="\n".join(want[i:i + 3000]) + "\n", timeout=900)
    open(marker, "w").close()


def card(c):
    print(f"cid={c['cid']} repo={c['repo']} lang={c['lang']} kind={c['kind']} doc={c['path']}\nsubject: {c['subject']}")
    print("--- stale passage\n" + c.get("stale_passage", "\n".join(c["old"])))
    print("--- fixed passage\n" + c.get("fixed_passage", "\n".join(c["new"])))
    print("--- changed: old", c["old_only"], "new", c["new_only"])


def main():
    cmd, cid = sys.argv[1], sys.argv[2]
    c = load()[cid]
    d = clone_dir(c["repo"])
    rev = c["sha"] + "^"
    prev = run(["git", "rev-parse", rev], cwd=d).stdout.strip()
    if cmd == "card":
        card(c)
    elif cmd == "grep":
        ensure_blobs(d, prev)
        g = sys.argv[4:] or CODE_GLOBS
        r = run(["git", "grep", "-n", "-I", "-E", "-e", sys.argv[3], prev, "--"] + g, cwd=d)
        L = [x.replace(prev + ":", "", 1)[:200] for x in r.stdout.split("\n") if x]
        print("\n".join(L[:40]) or "no matches")
        if len(L) > 40:
            print(f"[{len(L)} matches, first 40 shown]")
    elif cmd == "show":
        p, a, b = sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
        ensure_blobs(d, prev)
        r = run(["git", "show", f"{prev}:{p}"], cwd=d)
        if r.returncode:
            print("no such file")
            return
        L = r.stdout.split("\n")
        for i in range(max(1, a), min(b, len(L)) + 1):
            print(f"{i}: {L[i-1][:180]}")
        print(f"[{len(L)} lines]")
    elif cmd == "files":
        r = run(["git", "ls-tree", "-r", "--name-only", prev], cwd=d)
        L = [x for x in r.stdout.split("\n") if sys.argv[3].lower() in x.lower()]
        print("\n".join(L[:40]) or "none")


if __name__ == "__main__":
    main()
