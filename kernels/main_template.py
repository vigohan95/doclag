"""Private Kaggle kernel: run one model over the items. Filled in by push_run.sh. Two Ollama servers, one per T4,
unless SPLIT is true, in which case one server spans both GPUs for models that do not fit on one."""
import glob, json, os, shutil, subprocess, sys, time, urllib.request

MODEL = "__MODEL__"
EVAL_ARGS = "__EVAL_ARGS__"
AGENT_ARGS = "__AGENT_ARGS__"
SPLIT = __SPLIT__
AGENT_SCRIPT = "__AGENT_SCRIPT__"
PAR = __PAR__
DEADLINE = __DEADLINE__
W = "/kaggle/working"
t00 = time.time()


def sh(c, t=3000):
    r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
    print("$", c, "\n", r.stdout[-800:], r.stderr[-300:], flush=True)
    return r


src = glob.glob("/kaggle/input/**/run_eval.py", recursive=True)
print(src, flush=True)
D = os.path.dirname(src[0])
for f in glob.glob(D + "/*"):
    if os.path.isfile(f):
        shutil.copy(f, W)
os.chdir(W)
sh("apt-get install -y zstd >/dev/null 2>&1; curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -1", 900)
sh("ollama --version; nvidia-smi -L")
base = dict(os.environ, OLLAMA_KEEP_ALIVE="-1", OLLAMA_NUM_PARALLEL=str(PAR), OLLAMA_MAX_LOADED_MODELS="1", OLLAMA_FLASH_ATTENTION="1", OLLAMA_CONTEXT_LENGTH="16384")
ports = [11434] if SPLIT else [11434, 11435]
for i, p in enumerate(ports):
    e = dict(base, OLLAMA_HOST=f"127.0.0.1:{p}")
    if not SPLIT:
        e["CUDA_VISIBLE_DEVICES"] = str(i)
    else:
        e["OLLAMA_SCHED_SPREAD"] = "1"
    subprocess.Popen("ollama serve", shell=True, env=e, stdout=open(f"{W}/ollama{i}.log", "w"), stderr=subprocess.STDOUT)
time.sleep(8)
sh(f"OLLAMA_HOST=127.0.0.1:11434 ollama pull {MODEL} 2>&1 | tail -1", 3000)
sh("OLLAMA_HOST=127.0.0.1:11434 ollama list")
# the second server reads the same model store
tag = MODEL.replace(":", "_").replace("/", "_")
P = ",".join(map(str, ports))
workers = PAR * len(ports)
left = DEADLINE - (time.time() - t00)
for part in [x for x in EVAL_ARGS.split(";;") if x.strip()]:
    left = DEADLINE - (time.time() - t00)
    if left < 120:
        break
    c = f"python run_eval.py --model {MODEL} --ports {P} --workers {workers} --deadline {int(left)} --out {W}/raw_{tag}.jsonl {part} 2>&1 | tail -6"
    sh(c, 43000)
    sh("OLLAMA_HOST=127.0.0.1:11434 ollama ps; nvidia-smi --query-gpu=memory.used --format=csv")
left = DEADLINE - (time.time() - t00)
if AGENT_ARGS and left > 300:
    c = f"python {AGENT_SCRIPT} --model {MODEL} --ports {P} --workers {workers} --deadline {int(left)} --repos /tmp/repos --out {W}/agent_{tag}.jsonl {AGENT_ARGS} 2>&1 | tail -6"
    sh(c, 43000)
    shutil.rmtree("/tmp/repos", ignore_errors=True)
sh("OLLAMA_HOST=127.0.0.1:11434 ollama show " + MODEL + " | head -12; curl -s 127.0.0.1:11434/api/tags | head -c 600")
print("elapsed", int(time.time() - t00), flush=True)
