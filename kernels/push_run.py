"""Fill main_template.py and push a private GPU kernel.
usage: push_run.py <slug> <model> --eval "<args>" [--agent "<args>"] [--split] [--par 4] [--deadline 41000]
The private dataset hanvigo/doclag-run holds run_eval.py, run_agent.py and the items files."""
import argparse, json, os, subprocess

K = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("slug")
ap.add_argument("model")
ap.add_argument("--eval", default="")
ap.add_argument("--agent", default="")
ap.add_argument("--agent-script", default="run_agent.py")
ap.add_argument("--split", action="store_true")
ap.add_argument("--par", type=int, default=4)
ap.add_argument("--deadline", type=int, default=41000)
a = ap.parse_args()
d = os.path.join(K, a.slug)
os.makedirs(d, exist_ok=True)
s = open(os.path.join(K, "main_template.py"), encoding="utf-8").read()
s = s.replace("__MODEL__", a.model).replace("__EVAL_ARGS__", a.eval).replace("__AGENT_ARGS__", a.agent).replace("__SPLIT__", str(a.split)).replace("__AGENT_SCRIPT__", a.agent_script).replace("__PAR__", str(a.par)).replace("__DEADLINE__", str(a.deadline))
open(os.path.join(d, "main.py"), "w", encoding="utf-8").write(s)
meta = {"id": f"hanvigo/{a.slug}", "title": a.slug, "code_file": "main.py", "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
        "enable_internet": True, "dataset_sources": ["hanvigo/doclag-run"], "competition_sources": [], "kernel_sources": [], "model_sources": []}
json.dump(meta, open(os.path.join(d, "kernel-metadata.json"), "w"), indent=1)
env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
r = subprocess.run(["kaggle", "kernels", "push", "-p", d, "--accelerator", "NvidiaTeslaT4"], capture_output=True, text=True, env=env)
print(r.stdout[-300:], r.stderr[-300:])
