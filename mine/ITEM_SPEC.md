# Item writing spec

You turn one candidate (a documentation edit from a merged commit that changed no code) into one benchmark item, or reject it.
Be strict. Rejecting is normal: expect to keep a minority of candidates. Never invent evidence. Do not change repository files.

Tools (run from `D:/income-engine/work/hackathons/gemma4-paper/mine`):
- `python ctx.py card <cid>` prints the stale passage (before the commit), the fixed passage (after), the subject and the changed tokens.
- `python ctx.py grep <cid> "<regex>" ["*.py" ...]` searches the code at the parent commit.
- `python ctx.py show <cid> <path> <a> <b>` prints lines a..b at the parent commit with line numbers.
- `python ctx.py files <cid> <substring>` lists paths.
The first grep in a repository can take a minute, because it downloads that revision's blobs.

## Keep only if all of these hold
1. The stale passage makes a specific, checkable claim about what this project's code does: a default value, a name, a signature, a type, a return value, an error, an order, a condition, a limit, a CLI flag, a file path, a config key, or a behaviour.
2. The code at the parent commit shows that claim is FALSE, and that the fixed passage's replacement claim is TRUE. You must read the code to establish this. The commit subject alone is not evidence.
3. One contiguous span of one source file, at most 40 lines, is enough for a careful reader to establish the truth. Config files count as source if the code uses them (package.json, pyproject.toml, Cargo.toml).
4. The disagreement is a contradiction, not a clarification. Reject additions of new detail, added caveats, wording, examples that merely got better, and claims that were incomplete but not false.

## Reject with one of these reasons
`addition` (new information, old text not false), `wording`, `not-code` (claim about pricing, process, people, external services, third-party tools), `no-evidence` (code does not settle it, or needs more than one file), `code-disagrees` (the fixed passage does not match the code, or the stale passage does match it, for example docs written ahead of a later code change), `version-only`, `other`.

## Fields for a kept item
- `cid`
- `code_path`, `ev_start`, `ev_end`: the evidence span at the parent commit, 1-based, inclusive. Copy these from `ctx.py show` output.
- `evidence_note`: one sentence saying how those lines settle it. Name the value.
- `question`: one self-contained question about behaviour. It must not contain the truth or the stale value, must not mention documentation, and must be answerable from the evidence span and its neighbouring lines alone. Name the symbol or flag it asks about.
- `truth_option`: the correct answer, one short phrase.
- `stale_option`: the answer the stale passage implies, same style and about the same length as `truth_option`.
- `distractor_option`: a plausible wrong answer of the same type that neither passage states and that the code does not support.
- `truth_regex`, `stale_regex`: case-insensitive Python regexes that would find the truth or the stale value in a free-text answer. Keep them tight, for example `\b30\b` or `max_retries`. Use `null` if no short distinctive token exists. They must not both match the same natural answer.
- `category`: one of `default-value`, `name-or-path`, `signature`, `type-or-format`, `return-or-error`, `condition-or-order`, `limit-or-count`, `behaviour`.
- `doc_sentence`: the exact stale sentence or line that carries the false claim, copied from the stale passage.

Output format: one JSON object per line. Kept: all fields above plus `"decision":"keep"`. Rejected: `{"cid":..., "decision":"reject", "reason":...}`. Every assigned candidate gets exactly one line.

Note on rule 4: an omitted cap or exception counts as a contradiction only when the stale sentence gives a wrong answer for an ordinary input the code handles. Otherwise reject as `addition`.
If one candidate has several false claims, write the item about the clearest one.
Write the output file with a Python script that uses json.dumps, so regex backslashes are escaped correctly.
