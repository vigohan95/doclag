# Analysis plan (frozen before any Gemma 4 call on test items)

Purpose: fix the hypotheses, the primary metric and the tests before results exist. The sha256 of this file and of `eval/analyze.py`
are recorded in `RESULTS/FREEZE.txt`. No third party holds a timestamp for this file, so the freeze rests on our own record.

## Data
Items are built from merged commits that changed documentation and no code. A random 10% of repositories, with at least 30 items, is the dev split.
Prompts and parsing may change after looking at dev results. Test items are used once, after prompts are frozen. All confirmatory numbers come from test items.

## Primary metric
Strict accuracy per item and condition: the model picks the truth option in both option orders. Items are the unit.
"Misled": the stale option in both orders.

## Conditions
Q (question only), S (stale passage), F (fixed passage), C (code), SC (stale passage, then code), FC (fixed passage, then code), CS (code, then stale passage),
SCR (SC with the line "If the documentation and the source code disagree, the source code is correct."), FCR (FC with the same line).

## Confirmatory hypotheses, tested per model
- H1. Accuracy in FC is higher than in SC.
- H2. Accuracy in SC is lower than in C.
- H3. Accuracy in SCR is higher than in SC.
Test: exact two-sided McNemar on strict accuracy. Holm correction across H1 to H3 within each model. Effect size: paired difference with a 95% cluster bootstrap over repositories (10,000 resamples).

- H1f. The same comparison as H1 in free-form answers: answer contains the truth token and not the stale token, on items that have both regexes. Tested per model, one test, reported beside H1.
- H4 (tool loop). The agent gets the passage in its first message and may search the repository. Accuracy with the fixed passage in the fix commit is higher than with the stale passage in the parent commit. Exact two-sided McNemar per model.

## Reported whatever the outcome
Every condition for every model; choice shares (truth, stale, distractor, cannot tell); order-flip rate; free-form results; detection recall, false-alarm rate and paired correct rate; localisation accuracy against random; failed parses.

## Exploratory, labelled as such
Override rate (items solved from code alone that a stale passage turns wrong). Rescue rate. Break-even share of stale claims. Differential reading as a detector.
Splits by category, by language, by doc kind, by commit date before or after January 2025. Order effect (SC against CS). Cost of the rule when the passage is right (FC against FCR). Thinking mode. Differences between model sizes.

## Changes made after the dev run (46 dev items at most, 32 when this was written; no test item had been run)
Dev results led to three additions. Free-form answers became a confirmatory outcome, because the multiple-choice format may understate the effect. A longer code context (up to 200 lines each side, at most 16,000 characters) was added on a random 200-item subset, exploratory. The plain tool loop rarely reached the passage, so the preloaded arms became the H4 test and the plain arms are reported descriptively. Thinking was added to the detection prompt, exploratory.
Model coverage: E2B, E4B and 12B run all conditions. 26B A4B and 31B run C, SC, FC, SCR and detection, because of the free GPU budget; 31B on a random 250-item subset.

## Exclusions
Calls that fail after retries are retried in a later run. An unparsable answer counts as not correct and stays in the denominator.
Items may be removed only for a defect found in the item, independent of model output, and every removal is listed with its reason.
