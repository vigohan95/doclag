"""Tool-loop experiment. The same question is asked in the real repository at the parent commit (stale doc on disk)
and at the fix commit (fixed doc on disk). Nothing else differs, because the commit only changes documentation.

usage: run_agent.py --items agent_items.jsonl --repos DIR --model gemma4:e4b --out out.jsonl [--ports 11434,11435]
Expects DIR/<item id>/stale and DIR/<item id>/fixed, or builds them with git from GitHub.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from run_eval import options

SYS = """You are a coding agent working inside a software repository. You must answer a multiple-choice question about what the code in this repository actually does at this revision.

Reply with exactly one JSON object per turn and nothing else. The available actions are:
{"tool":"ls","path":"<dir>"}                         list a directory
{"tool":"grep","pattern":"<regex>","path":"<dir>"}   search text files, returns file:line:text
{"tool":"read","path":"<file>","start":1,"end":120}  read lines of a file
{"tool":"answer","choice":"<A|B|C|D>"}               give your final answer and stop

You have at most %d turns. On the last turn you must answer."""
MAX_OUT = 6000


def sh(a, cwd=None, timeout=900):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def build(item, root):
    base = os.path.join(root, item["id"])
    s, f = base + "/stale", base + "/fixed"
    if os.path.isdir(s) and os.path.isdir(f):
        return s, f
    os.makedirs(base, exist_ok=True)
    g = base + "/g.git"
    if not os.path.isdir(g):
        r = sh(["git", "clone", "-q", "--bare", "--filter=blob:none", f"https://github.com/{item['repo']}.git", g])
        if r.returncode:
            raise RuntimeError(r.stderr[-200:])
    for d, sha in ((s, item["parent_sha"]), (f, item["fix_sha"])):
        r = sh(["git", "--git-dir", g, "worktree", "add", "-q", "--detach", "-f", os.path.abspath(d), sha])
        if r.returncode:
            raise RuntimeError(r.stderr[-200:])
        gitfile = os.path.join(d, ".git")
        if os.path.exists(gitfile):
            os.remove(gitfile)
    return s, f


def safe(root, p):
    p = (p or ".").lstrip("/\\")
    full = os.path.normpath(os.path.join(root, p))
    if not (full == root or full.startswith(root + os.sep)):
        return None
    return full


def tool(root, act):
    t = act.get("tool")
    if t == "ls":
        d = safe(root, act.get("path"))
        if not d or not os.path.isdir(d):
            return "error: not a directory"
        return "\n".join(sorted(x + ("/" if os.path.isdir(os.path.join(d, x)) else "") for x in os.listdir(d))[:200])
    if t == "grep":
        d = safe(root, act.get("path"))
        pat = str(act.get("pattern") or "")
        if not d or not pat:
            return "error: bad grep"
        r = sh(["grep", "-rnIE", "--exclude-dir=node_modules", "--exclude-dir=.git", "-m", "20", "--", pat, d], timeout=120)
        lines = [l.replace(root + os.sep, "")[:220] for l in r.stdout.split("\n") if l][:40]
        return "\n".join(lines) or "no matches"
    if t == "read":
        f = safe(root, act.get("path"))
        if not f or not os.path.isfile(f):
            return "error: no such file"
        try:
            st = max(1, int(act.get("start") or 1))
            en = min(st + 149, int(act.get("end") or st + 119))
        except Exception:
            st, en = 1, 120
        L = open(f, encoding="utf-8", errors="replace").read().split("\n")
        return "\n".join(f"{i}: {L[i-1][:200]}" for i in range(st, min(en, len(L)) + 1)) + f"\n[file has {len(L)} lines]"
    return "error: unknown tool"


def chat(port, model, msgs, num_ctx):
    body = {"model": model, "stream": False, "think": False, "format": "json", "keep_alive": -1,
            "options": {"temperature": 0, "seed": 7, "num_ctx": num_ctx, "num_predict": 300}, "messages": msgs}
    for a in range(3):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=1200))["message"].get("content", "")
        except Exception as e:
            err = repr(e)[:150]
            time.sleep(3)
    return json.dumps({"tool": "error", "detail": err})


def episode(item, root, arm, port, model, max_turns, num_ctx):
    order = int(hashlib.sha256(item["id"].encode()).hexdigest(), 16) % 2
    opts = options(item, order)
    letters = "ABCD"
    body = "\n".join(f"{letters[i]}) {o[1]}" for i, o in enumerate(opts))
    pre = ""
    if arm == "pre-stale":
        pre = f"Documentation excerpt from {item['doc_path']}:\n<<<\n{item['stale_passage']}\n>>>\n\n"
    elif arm == "pre-fixed":
        pre = f"Documentation excerpt from {item['doc_path']}:\n<<<\n{item['fixed_passage']}\n>>>\n\n"
    q = f"Repository: {item['repo']}\n{pre}Question: {item['question']}\n\n{body}"
    msgs = [{"role": "system", "content": SYS % max_turns}, {"role": "user", "content": q}]
    trace = []
    choice = None
    for turn in range(max_turns):
        txt = chat(port, model, msgs, num_ctx)
        try:
            act = json.loads(txt)
        except Exception:
            act = {"tool": "bad-json"}
        if act.get("tool") == "answer":
            l = str(act.get("choice", "")).strip().upper()[:1]
            choice = {letters[i]: o[0] for i, o in enumerate(opts)}.get(l)
            trace.append({"t": turn, "act": act})
            break
        obs = tool(root, act) if act.get("tool") in ("ls", "grep", "read") else 'error: reply with one JSON action'
        if len(obs) > MAX_OUT:
            obs = obs[:MAX_OUT] + "\n[truncated]"
        doc_seen = item["doc_path"] in obs or (act.get("path") or "").endswith(item["doc_path"])
        marker = item.get("marker_stale") if arm in ("stale", "pre-stale") else item.get("marker_fixed")
        trace.append({"t": turn, "act": act, "obs_len": len(obs), "doc_seen": bool(doc_seen), "code_seen": item["code_path"] in obs or (act.get("path") or "").endswith(item["code_path"]),
                      "passage_seen": bool(marker and marker in obs)})
        left = max_turns - turn - 1
        msgs.append({"role": "assistant", "content": txt})
        msgs.append({"role": "user", "content": f"Result:\n{obs}\n\n{left} turns left." + (" You must answer now." if left == 1 else "")})
    return {"model": model, "id": item["id"], "arm": arm, "order": order, "choice": choice, "turns": len(trace), "trace": trace,
            "read_doc": any(t.get("doc_seen") and t["act"].get("tool") == "read" for t in trace),
            "read_code": any(t.get("code_seen") and t["act"].get("tool") == "read" for t in trace),
            "saw_passage": any(t.get("passage_seen") for t in trace)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--repos", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ports", default="11434")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--deadline", type=float, default=0)
    a = ap.parse_args()
    items = [json.loads(l) for l in open(a.items, encoding="utf-8")]
    ports = [int(p) for p in a.ports.split(",")]
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out, encoding="utf-8"):
            r = json.loads(l)
            done.add((r["id"], r["arm"]))
    out = open(a.out, "a", encoding="utf-8")
    lock = threading.Lock()
    t0 = time.time()
    cnt = [0]

    def work(ix):
        i, it = ix
        if a.deadline and time.time() - t0 > a.deadline:
            return
        try:
            s, f = build(it, a.repos)
        except Exception as e:
            with lock:
                out.write(json.dumps({"model": a.model, "id": it["id"], "arm": "build-failed", "error": str(e)}) + "\n")
                out.flush()
            return
        for arm, root in (("stale", s), ("fixed", f), ("pre-stale", s), ("pre-fixed", f)):
            if (it["id"], arm) in done:
                continue
            r = episode(it, os.path.abspath(root), arm, ports[i % len(ports)], a.model, a.max_turns, a.num_ctx)
            with lock:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
                out.flush()
                cnt[0] += 1
                if cnt[0] % 20 == 0:
                    print(cnt[0], int(time.time() - t0), flush=True)
        shutil.rmtree(os.path.join(a.repos, it["id"]), ignore_errors=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(work, enumerate(items)))
    print("done", cnt[0], int(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
