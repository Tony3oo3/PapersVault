---
name: trend-report
description: Measure and explain how a topic, method or practice evolves across the conferences in the PapersVault ("how has X moved since 2024?", "what is new in CVPR 2026?", "is Y declining?"). Numbers come from vault.py trend/sql, explanations from reading a sample of notes.
---

# Trend report

Read `../paper-search/REFERENCE.md` first, especially "Data caveats". Run `vault.py status`.

## A named topic ("how has X evolved?")

1. **Write the inclusion rule first** ("papers whose method uses 3DGS as its scene
   representation", not "papers mentioning 3DGS"), then define the topic two ways:
   - a text query restricted to the main claim:
     `trend --query '{title key_contribution}: ("gaussian splatting" OR 3dgs)' --sample 20`
   - the founding work: `citers "<partial title>"` to find the exact cited title(s), then
     `trend --cites "<title>" --kind builds_on --sample 20`
   For each, count how many of the 20 sampled papers meet the rule (strict and lenient if
   borderline cases matter) and report it with the numbers. If below ~15/20, tighten: restrict
   the text query to `{title key_contribution}:`, drop ambiguous synonyms, then re-sample.
   When the two definitions disagree late in the period, trust the text query for the level:
   mature topics cite the founding paper's descendants instead of the paper itself.
2. **Read the table correctly:** compare shares, not counts, and above all the same venue
   across years (the `prev` column; `--venue CVPR ECCV ICCV` for the vision family). Drop
   INCOMPLETE rows. Say when the trend is the same in both families and when it differs.
3. **Explain what changed.** Measure it, then read it:
   - sub-topics inside the topic: `trend --query '<sub-topic>' --within '<topic query>' --venue ...`
     for each candidate sub-topic (feed-forward, editing, avatars, ...);
   - what the topic's papers build on, early vs late: the "Rising cited works within a topic"
     recipe in the reference;
   - then pull papers from different points in time (first adopters, the latest edition, a
     few in between) with `search '<topic query>' --venue ... --year ...`, and screen them with
     `show ID ... --sections problem method --max-chars 600` (~15-30 papers).
   Newly introduced datasets (`datasets_introduced`) are a good signal for benchmark-driven
   topics, less so for representation or method topics.
   When one paper marks a turning point, read what it actually changed in its own words:
   `vault.py ocr ID --grep '<method terms>'`.
4. **Write the report** (below).

## An open question ("what is new in ECCV 2026?", "what is rising?")

1. Rank candidate signals with SQL (recipes in the reference): fastest-rising `builds_on`
   targets between two comparable editions; papers with `task_novelty = 'new'` in the latest
   editions (`search ... --new`); newly introduced datasets that later papers evaluate on.
2. Keep the 3-6 strongest signals, confirm each with `trend` (and `--sample`), then explain
   each as in steps 3-4 above.

## The report

- One-paragraph summary first: what changed, how much, since when.
- The numbers: the `trend` table(s) or a compact version of them, with the query and its
  sampled precision, and the caveats that apply (incomplete edition, venue mix).
- What changed and when, with 2-5 representative papers per phase (paper ID, one line each).
- Open questions, drawn from the notes' "Why It Matters / Open Questions" sections.
- Deliver it in the chat unless the user asks for a file or a page.
