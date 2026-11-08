# DocLag

DocLag is a set of 443 documentation-versus-code contradictions that maintainers fixed in 185 open-source repositories. Each item pairs the stale passage with the passage that replaced it, in a commit that changed no code, and asks one question about what the code does.

It comes with the mining pipeline, the evaluation harness, every raw model output from the paper's runs on Gemma 4 (E2B, E4B, 12B, 26B A4B, 31B), and the frozen analysis plan.

## Five-minute check

```
python eval/report.py          # rebuilds results/final/numbers.json from results/raw/*.jsonl
python eval/figures.py         # redraws the two figures
```
Both use only the Python standard library plus matplotlib for the figures. `report.py` needs the raw files laid out as `results/main/<run>/raw_*.jsonl`; `results/raw/` holds them flattened as `<run>__raw_*.jsonl`.

## Data

`data/items_test.jsonl` (397 items, 161 repositories) and `data/items_dev.jsonl` (46 items, 24 repositories). Fields: `repo`, `license`, `parent_sha`, `fix_sha`, `doc_path`, `stale_passage`, `fixed_passage`, `code_path`, `ev_start`/`ev_end` (evidence span at the parent commit), `code_window`, `code_long`, `question`, `truth_option`, `stale_option`, `distractor_option`, `truth_regex`, `stale_regex`, `category`, `kind` (doc page or code comment), `verify` (how "no code changed" was checked), `gold_sentences`.

Questions, options and patterns were written by Claude Opus 5.5 and checked as described in the paper: a blind solver (Claude Sonnet) reading only the code agreed with 446 of 452 drafts, and 40 runtime probes on installed packages all agreed (`results/exec/`).

Licences: every item comes from a repository whose licence GitHub reports as MIT, Apache-2.0, BSD-2/3-Clause, ISC, MPL-2.0, Unlicense or CC0. `data/ATTRIBUTION.tsv` lists repository, licence and commits. Passages and code excerpts remain under their projects' licences. Some projects licence documentation separately; check before reuse outside research.

## Running the models

`kernels/` holds the private Kaggle notebook template that installs Ollama on two T4 GPUs, pulls a `gemma4` tag and runs `eval/run_eval.py` and `eval/run_agent.py`. `kernels/push_run.py <slug> <model> --eval "<args>"` pushes one run. Models: `gemma4:e2b` (b37049369adf), `gemma4:e4b` (dc35e8d9c606), `gemma4:12b` (6114515d63c1), `gemma4:26b` (001e5dafc3c7), `gemma4:31b` (17ba34c06c80), all Q4_K_M.

## Mining your own

`mine/mine1.py` (doc-only commits), `mine/prefilter.py`, then triage, `mine/cards.py` (code pre-search), item writing per `mine/ITEM_SPEC.md`, `mine/build_items.py` (deterministic checks), `mine/audit.py` (blind solver), `eval/make_splits.py`.

## Plan and hashes

`paper/PREREG.md` was frozen before any test call; `paper/FREEZE.txt` has its sha256 and those of the analysis code and item files. `paper/PREREG-ADDENDUM.md` lists what was added after results were seen.

## Licence

Code: Apache-2.0. Data: see above.
