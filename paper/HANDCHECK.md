# Sample check of items

Who did it: the Claude session that built the dataset (model claude-opus-5-5). This is not a human check. Do not describe it as human review.
What: 30 items drawn at random (seed 20261107) from the 443 frozen items. For each, the stale sentence, question, truth option, stale option and the evidence lines at the parent commit were read and compared.
Result: 30 of 30 have a truth option supported by the evidence lines and a stale option contradicted by them.
Weak but kept: 1 item asks a proxy question (a24: LlamaFactory, where `metrics.txt` lives, standing in for a claim about the requirements folder). 2 items ask for a file path that the code header in the prompt already shows (docker/compose, starship). Items were frozen unchanged.
Sample ids: `work/hackathons/gemma4-paper/scratch/handcheck_ids.json`.
