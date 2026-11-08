"""Two static figures for the paper from results/final/numbers.json. Values are printed on the marks; the
same numbers are in numbers.json, so the figures carry no number that is not in a results file."""
import json, os
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
N = json.load(open(os.path.join(B, "results", "final", "numbers.json"), encoding="utf-8"))
out = os.path.join(B, "results", "final")
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COL = {"C": "#2a78d6", "FC": "#1baf7a", "SC": "#eb6834"}
ORDER = ["gemma4:e2b", "gemma4:e4b", "gemma4:12b", "gemma4:26b", "gemma4:31b"]
LAB = {"gemma4:e2b": "E2B", "gemma4:e4b": "E4B", "gemma4:12b": "12B", "gemma4:26b": "26B A4B", "gemma4:31b": "31B*"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})

# Figure 1: strict accuracy by model for code only, fixed passage + code, stale passage + code
ms = [m for m in ORDER if m in N["models"]]
fig, ax = plt.subplots(figsize=(6.4, 2.9), dpi=200)
fig.patch.set_facecolor(SURF)
ax.set_facecolor(SURF)
for j, m in enumerate(ms):
    t = N["models"][m]["mcq"]
    vals = {k: t[k]["strict_rate"] for k in ("C", "FC", "SC") if k in t}
    ax.plot([vals["SC"], vals["FC"]], [j, j], color=GRID, lw=2, zorder=1)
    for k, v in vals.items():
        ax.scatter(v, j, s=46, color=COL[k], zorder=3, edgecolor=SURF, linewidth=1.5)
    ax.text(vals["SC"] - 0.012, j + 0.22, f"{vals['SC']:.2f}", ha="right", va="center", color=INK2, fontsize=7.5)
    ax.text(vals["FC"] + 0.012, j + 0.22, f"{vals['FC']:.2f}", ha="left", va="center", color=INK2, fontsize=7.5)
ax.set_yticks(range(len(ms)), [LAB[m] for m in ms], color=INK)
ax.set_xlim(0.45, 1.0)
ax.set_ylim(-0.6, len(ms) - 0.4)
ax.invert_yaxis()
ax.grid(axis="x", color=GRID, lw=0.6)
ax.set_axisbelow(True)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.set_xlabel("strict accuracy (truth option in both orders)")
handles = [plt.Line2D([], [], marker="o", ls="", color=COL[k], label=l) for k, l in (("FC", "fixed passage + code"), ("C", "code only"), ("SC", "stale passage + code"))]
ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8, handletextpad=0.3)
fig.tight_layout()
fig.savefig(os.path.join(out, "fig1_models.png"), facecolor=SURF)

# Figure 2: tool loop arms
arms_order = [("stale", "no passage given"), ("pre-fixed", "fixed passage given"), ("pre-stale", "stale passage given"), ("pre-stale-rule", "stale + instruction"), ("pre-stale-gate", "stale + read-code gate")]
am = [m for m in ORDER if m in N["agent"]]
fig, axes = plt.subplots(1, len(am), figsize=(3.2 * len(am), 2.6), dpi=200, sharey=True, squeeze=False)
fig.patch.set_facecolor(SURF)
for ax, m in zip(axes[0], am):
    ax.set_facecolor(SURF)
    A = N["agent"][m]["arms"]
    xs = [(l, A[k]["acc"]) for k, l in arms_order if k in A]
    for i, (l, v) in enumerate(xs):
        c = "#2a78d6" if "no passage" in l else ("#1baf7a" if "fixed" in l else "#eb6834")
        ax.barh(i, v, color=c, height=0.62)
        ax.text(v + 0.015, i, f"{v:.2f}", va="center", color=INK2, fontsize=7.5)
    ax.set_yticks(range(len(xs)), [l for l, _ in xs], color=INK, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.set_title(f"{LAB[m]}, n={A['stale']['n']} questions", color=INK, fontsize=9, loc="left")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("accuracy in the tool loop")
fig.tight_layout()
fig.savefig(os.path.join(out, "fig2_agent.png"), facecolor=SURF)
print("ok", ms, am)
