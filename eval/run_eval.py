"""DocLag evaluation harness. Talks to one or more Ollama servers, one JSON line per call, resumable.

usage: run_eval.py --items items.jsonl --model gemma4:e4b --out out.jsonl --tasks mcq,free,detect,locate
                   [--conds Q,S,F,C,SC,FC,CS,SCR] [--think-conds SC,FC,C] [--ports 11434,11435] [--workers 8]
Every prompt is built here, so a condition differs from its pair only in the passage text.
"""
import argparse, hashlib, json, os, random, re, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

SYS = (
    "You answer questions about what a software project's code actually does at the revision shown. "
    "Use the material given. Follow the requested output format exactly."
)
RULE = "If the documentation and the source code disagree, the source code is correct.\n\n"
CANT = "The material given does not determine the answer"


def doc_block(item, which):
    p = item["stale_passage"] if which == "S" else item["fixed_passage"]
    return f"Documentation excerpt ({item['doc_path']}):\n<<<\n{p}\n>>>\n\n"


def code_block(item, long=False):
    w = item["code_long"] if long else item["code_window"]
    return f"Source code ({item['code_path']}):\n<<<\n{w}\n>>>\n\n"


def context(item, cond):
    if cond == "Q":
        return ""
    if cond == "S":
        return doc_block(item, "S")
    if cond == "F":
        return doc_block(item, "F")
    if cond == "C":
        return code_block(item)
    if cond == "SC":
        return doc_block(item, "S") + code_block(item)
    if cond == "FC":
        return doc_block(item, "F") + code_block(item)
    if cond == "CS":
        return code_block(item) + doc_block(item, "S")
    if cond == "CF":
        return code_block(item) + doc_block(item, "F")
    if cond == "CL":
        return code_block(item, True)
    if cond == "SCL":
        return doc_block(item, "S") + code_block(item, True)
    if cond == "FCL":
        return doc_block(item, "F") + code_block(item, True)
    if cond == "SCR":
        return RULE + doc_block(item, "S") + code_block(item)
    if cond == "FCR":
        return RULE + doc_block(item, "F") + code_block(item)
    raise ValueError(cond)


def options(item, order):
    """Four options. CANT is always last; the three others are permuted by a per-item seed.
    order 0 and order 1 put the truth and the stale claim in swapped slots."""
    rng = random.Random(hashlib.sha256(item["id"].encode()).hexdigest())
    trio = [("truth", item["truth_option"]), ("stale", item["stale_option"]), ("distractor", item["distractor_option"])]
    rng.shuffle(trio)
    if order == 1:
        i = [k for k, v in enumerate(trio) if v[0] == "truth"][0]
        j = [k for k, v in enumerate(trio) if v[0] == "stale"][0]
        trio[i], trio[j] = trio[j], trio[i]
    trio.append(("cant", CANT))
    return trio


def mcq_prompt(item, cond, order):
    opts = options(item, order)
    letters = "ABCD"
    body = "\n".join(f"{letters[i]}) {o[1]}" for i, o in enumerate(opts))
    q = context(item, cond) + f"Question about {item['repo']}: {item['question']}\n\n{body}\n\nReply with the letter of the correct option only."
    return q, {letters[i]: o[0] for i, o in enumerate(opts)}


def parse_letter(text):
    t = (text or "").strip()
    m = re.search(r"(?:answer|option)\s*(?:is|:)?\s*\**\(?([ABCD])\b", t, re.I)
    if m:
        return m[1].upper()
    m = re.match(r"\W*([ABCD])\b", t)
    if m:
        return m[1]
    m = re.findall(r"\b([ABCD])\)", t)
    if len(set(m)) == 1:
        return m[0]
    return None


def free_prompt(item, cond):
    return context(item, cond) + f"Question about {item['repo']}: {item['question']}\n\nAnswer in one short sentence. If the material does not determine the answer, say so."


def score_free(item, text):
    t = text or ""
    tr = bool(re.search(item["truth_regex"], t, re.I)) if item.get("truth_regex") else None
    st = bool(re.search(item["stale_regex"], t, re.I)) if item.get("stale_regex") else None
    return {"truth_hit": tr, "stale_hit": st}


def detect_prompt(item, which):
    return (
        doc_block(item, which)
        + code_block(item)
        + "Does the documentation excerpt state anything that contradicts the source code shown? "
        "Reply with YES or NO only."
    )


def parse_yes(text):
    m = re.search(r"\b(yes|no)\b", (text or ""), re.I)
    return m[1].upper() if m else None


def split_sentences(p):
    parts = re.split(r"(?<=[.!?:])\s+|\n+", p)
    return [x.strip() for x in parts if len(x.strip()) > 2]


def locate_prompt(item, which):
    sents = split_sentences(item["stale_passage"] if which == "S" else item["fixed_passage"])
    body = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sents))
    return (
        code_block(item)
        + f"Numbered statements from the documentation ({item['doc_path']}):\n{body}\n\n"
        "Which statement contradicts the source code? Reply with its number, or 0 if none does. Reply with the number only."
    ), sents


class Client:
    def __init__(self, ports, model, num_ctx, num_predict, think_predict):
        self.ports = ports
        self.model = model
        self.num_ctx = num_ctx
        self.np = num_predict
        self.tp = think_predict
        self.i = 0
        self.lock = threading.Lock()

    def chat(self, prompt, think=False):
        with self.lock:
            port = self.ports[self.i % len(self.ports)]
            self.i += 1
        body = {
            "model": self.model,
            "stream": False,
            "think": bool(think),
            "keep_alive": -1,
            "options": {"temperature": 0, "seed": 7, "num_ctx": self.num_ctx, "num_predict": self.tp if think else self.np},
            "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}],
        }
        last = None
        for a in range(4):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
                r = json.load(urllib.request.urlopen(req, timeout=1800))
                m = r.get("message", {})
                return {
                    "text": m.get("content", ""),
                    "thinking_chars": len(m.get("thinking") or ""),
                    "thinking": (m.get("thinking") or "")[:1500],
                    "prompt_tokens": r.get("prompt_eval_count"),
                    "out_tokens": r.get("eval_count"),
                    "done_reason": r.get("done_reason"),
                }
            except Exception as e:
                last = repr(e)[:200]
                time.sleep(3 * (a + 1))
        return {"text": "", "error": last}


def jobs(items, a):
    for it in items:
        if "mcq" in a.tasks:
            for c in a.conds:
                for o in (0, 1):
                    yield dict(task="mcq", item=it, cond=c, order=o, think=False)
            for c in a.think_conds:
                for o in a.think_orders:
                    yield dict(task="mcq", item=it, cond=c, order=o, think=True)
        if "free" in a.tasks:
            for c in a.free_conds:
                yield dict(task="free", item=it, cond=c, order=0, think=False)
        if "detect" in a.tasks:
            for w in "SF":
                yield dict(task="detect", item=it, cond=w, order=0, think=False)
        if "detectT" in a.tasks:
            for w in "SF":
                yield dict(task="detect", item=it, cond=w, order=0, think=True)
        if "locate" in a.tasks:
            for w in "SF":
                yield dict(task="locate", item=it, cond=w, order=0, think=False)


def key(j):
    return f"{j['item']['id']}|{j['task']}|{j['cond']}|{j['order']}|{int(j['think'])}"


def do(j, cl):
    it = j["item"]
    rec = {"model": cl.model, "id": it["id"], "task": j["task"], "cond": j["cond"], "order": j["order"], "think": j["think"]}
    if j["task"] == "mcq":
        p, m = mcq_prompt(it, j["cond"], j["order"])
        r = cl.chat(p, j["think"])
        l = parse_letter(r["text"])
        rec.update(letter=l, choice=m.get(l) if l else None)
    elif j["task"] == "free":
        p = free_prompt(it, j["cond"])
        r = cl.chat(p, False)
        rec.update(score_free(it, r["text"]))
    elif j["task"] == "detect":
        p = detect_prompt(it, j["cond"])
        r = cl.chat(p, j["think"])
        rec.update(verdict=parse_yes(r["text"]))
    else:
        p, sents = locate_prompt(it, j["cond"])
        r = cl.chat(p, False)
        m = re.search(r"\d+", r["text"] or "")
        rec.update(pick=int(m[0]) if m else None, n_sent=len(sents))
    rec["prompt_sha"] = hashlib.sha256(p.encode()).hexdigest()[:12]
    rec.update({k: r.get(k) for k in ("text", "thinking_chars", "thinking", "prompt_tokens", "out_tokens", "done_reason", "error")})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", default="mcq,free,detect,locate")
    ap.add_argument("--conds", default="Q,S,F,C,SC,FC,CS,SCR")
    ap.add_argument("--think-conds", default="")
    ap.add_argument("--think-orders", default="0,1")
    ap.add_argument("--free-conds", default="C,SC,FC")
    ap.add_argument("--ports", default="11434")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-predict", type=int, default=64)
    ap.add_argument("--think-predict", type=int, default=3072)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--deadline", type=float, default=0, help="stop after this many seconds")
    a = ap.parse_args()
    a.tasks = a.tasks.split(",")
    a.conds = [c for c in a.conds.split(",") if c]
    a.think_conds = [c for c in a.think_conds.split(",") if c]
    a.think_orders = [int(x) for x in a.think_orders.split(",")]
    a.free_conds = [c for c in a.free_conds.split(",") if c]
    items = [json.loads(l) for l in open(a.items, encoding="utf-8")]
    if a.limit:
        items = items[: a.limit]
    done = set()
    if os.path.exists(a.out):
        for l in open(a.out, encoding="utf-8"):
            r = json.loads(l)
            if not r.get("error"):
                done.add(f"{r['id']}|{r['task']}|{r['cond']}|{r['order']}|{int(r['think'])}")
    todo = [j for j in jobs(items, a) if key(j) not in done]
    print(len(items), "items", len(todo), "calls to do", flush=True)
    cl = Client([int(p) for p in a.ports.split(",")], a.model, a.num_ctx, a.num_predict, a.think_predict)
    out = open(a.out, "a", encoding="utf-8")
    t0 = time.time()
    lock = threading.Lock()
    n = [0]

    def work(j):
        if a.deadline and time.time() - t0 > a.deadline:
            return
        r = do(j, cl)
        with lock:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.flush()
            n[0] += 1
            if n[0] % 200 == 0:
                print(n[0], int(time.time() - t0), flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(work, todo))
    print("done", n[0], int(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
