# Changes after the first run

Each entry says what changed and why. No probe decision logic changes unless stated.

## Run 1 -> run 2 (runner only, no probe touched)
- Run 1: all 40 INSTALL_FAIL in under 5 s. Kaggle's system Python is 3.13 and has no ensurepip, so `python -m venv` failed. Nothing reached pip or a probe.
- Runner now builds each venv with uv (`uv venv --seed --python 3.11`), on a pinned Python 3.11, which also suits the older commits.
- Removed `--ignore-requires-python` from the dspy f603036 install, since 3.11 meets its `requires-python`.

## Run 2 -> run 3 (runner only, no probe touched)
- Run 2: all 40 INSTALL_FAIL again. My edit that installs uv at kernel start did not land in the template, so the uv binary did not exist. Added it properly, and the runner uses a `uv` already on PATH if there is one.

## Run 3 -> run 4 (install fixes for the 3 items that did not reach a verdict; probe code unchanged)
Run 3 gave 37 TRUTH, 1 INSTALL_FAIL, 2 PROBE_ERROR. None of the three failures was a verdict, and no probe text changed.
- 016143422b (whisper): install failed because setup.py imports `pkg_resources`, which current setuptools dropped. Added `setuptools<81` in the venv and `--no-build-isolation`.
- 68232d9bdb (langgraph): `import langgraph.graph` raised an MRO TypeError, because the newest langchain-core does not work with this July 2025 commit. Pinned `langchain-core==0.3.68`, the last release before the commit.
- ecc08c9237 (Scrapling): import raised ModuleNotFoundError for `browserforge`, which the `fetchers` extra no longer pulls in. Added it to the install.

## Run 4 -> run 5
68232d9bdb (langgraph) gave TRUTH in run 4 with the pin. Two items still had no verdict, both probe or harness mistakes; decision branches unchanged.
- 016143422b (whisper), probe fix: `import whisper.transcribe as t` bound the `transcribe` function, not the module, so `t.cli` raised AttributeError. Now `from whisper.transcribe import cli`.
- ecc08c9237 (Scrapling), probe fix: `scrapling/engines/_browsers/_base.py` calls `camoufox.pkgman.installed_verstr()` at import and raises when no Camoufox browser is installed. The probe now stubs that one function before importing. It only supplies a version string, and has nothing to do with how `fetch` reads its keyword arguments.

## Run 5 -> run 6 (no change to any probe)
Run 5 gave TRUTH for both remaining items. Run 6 reruns all 40 final probes in one kernel, so exec_results.jsonl comes from a single run of the exact run_probes.py on disk.
