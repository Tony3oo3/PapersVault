---
name: novelty-check
description: Check whether a research idea of the user's is new against the PapersVault ("is this idea new?", "has anyone done X?", "check my idea", "how novel is ...", "what is the closest work to ..."). Interactive. It restates the idea and asks sharpening questions, searches each part of it, reads the closest papers' OCR, discusses the neighbours with the user, and gives a verdict per part with evidence, plus what a reviewer would ask.
---

# Novelty check

Read `../paper-search/REFERENCE.md` first, then run `vault.py status`. Read the "Current
projects" section of `research_topics/_me.md` if it exists.

This is a **conversation**. It stops at three checkpoints for the user's answer. Use
AskUserQuestion when it is available (2-4 options, plus the free-text answer it always offers);
otherwise ask one short question in chat and wait. Never run all the steps in one go.

You are the colleague who knows the literature and wants the idea to succeed. Be specific and
honest: "this is done" is a useful answer when it is true, and it always comes with the paper
that did it and a way to move on.

## Steps

1. **Restate the idea as a claim.** From whatever the user gave (a sentence, a sketch, a draft,
   a figure), write:
   - **Task and setting**: the input, the output, and the assumptions (data, supervision,
     compute, real-time ...).
   - **Mechanism**: what the method actually does, in one or two sentences.
   - **Claimed novelty**: what the user believes is new.
   - **Evidence**: the experiment that would prove it, and the baseline it must beat.

   **Checkpoint 1.** Show the restatement and ask 2-4 questions, only those whose answer changes
   the search:
   - Which part do you consider new: the task, the mechanism, the combination, or the setting?
   - What is the closest work you already know? This is where the search starts.
   - Which constraint is essential (training-free, single image, no 3D supervision, on-device,
     ...)? Papers that drop it are not competitors.
   - Is this aimed at a method paper, a new task or benchmark, or an analysis?
2. **Split it into novelty axes.** Each axis is searched on its own, because novelty is usually
   a combination ("X for Y under Z") and each part has its own neighbours:
   - *problem*: has this task or setting been posed?
   - *mechanism*: has this technique been used, for any task?
   - *combination*: has this mechanism been applied to this problem?
   - *setting / constraint*: has it been done under this constraint?
   - *evaluation*: is there already a benchmark or protocol for it?
3. **Search each axis.** Commands and query syntax are in the reference.
   - 3-5 `search` queries per axis, in the field's terms (translate the user's wording), using
     `{title key_contribution}:` for precision when a query is broad;
   - `like --works "<title>" ...` with the works the idea builds on, i.e. the methods it
     extends: papers sharing those citations are the closest neighbours;
   - `citers "<work or ID>" --kind builds_on` on the closest base methods: their direct
     follow-ups;
   - `search ... --new` for the problem axis (papers that define a new task);
   - `trend --query '<core query>' --sample 20` with an inclusion rule written first (as in
     the reference): how crowded the area is and whether it is rising. Report the sampled
     precision with the numbers. A crowded, rising area raises the bar.
   - for each key base method, `citers "<short name>"` as well as `citers <ID>`: citation
     linking misses some title variants (see the reference).

   Put `--ids-file` lists in `$TMPDIR` or your scratchpad, not in the vault.

   Screen the cards. Read the ~15 nearest neighbours with
   `show ID ... --sections problem method --max-chars 900`.
4. **Close reading via the OCR.** For the 3-5 closest papers, notes are too coarse to tell "the
   same idea" from "a different idea", and they can mislead: a note may say "accumulated
   during training" when the paper's algorithm computes it after training. A note's
   description of a mechanism is never enough to decide same or different. Read the method
   itself: `vault.py ocr ID --grep '<the mechanism's terms>' --context 5`
   (`--grep 'Algorithm' --context 20` for pseudo-code), or the whole OCR when the overlap is
   real. Use `--supplemental` if the detail may be in the appendix. Write down, per paper,
   what is the same and what is different, at the level of the mechanism.
5. **Checkpoint 2: the neighbours.** Show each close paper as:
   `ID · Name (venue) · same: ... · different: ...`, closest first. Then ask whether the
   differences you found are the ones the user cares about, and whether any of these papers
   changes the idea. This is often where the idea gets sharper ("with constraint Z, none of
   these apply"). If the idea shifts, go back to step 3 for the changed axes only, at most
   twice.
6. **Verdict.** One line per axis: **done** / **partially done** / **open in the vault**, each
   with the paper IDs that support it. Then:
   - **Overall**: 2-3 sentences. Say whether the contribution would read as new, incremental,
     or already published.
   - **The delta**: the one sentence the paper's introduction could honestly claim ("Unlike
     [A] and [B], which ..., we ...").
   - **Baselines a reviewer will demand**: the `compares_to` lists of the closest neighbours,
     via the "Most common baselines in a set" recipe with the neighbours' IDs.
   - **The most likely reviewer objection**, and what experiment answers it.
7. **Coverage caveat, always stated.** The vault holds CVPR, ICCV, ECCV, ICLR, ICML and
   NeurIPS from 2024 on. It has no arXiv preprints, no workshops, no other venues (SIGGRAPH,
   TPAMI, CoRL, ACL, ...) and nothing older. Robotics venues (ICRA, IROS, RA-L, CoRL, RSS) matter
   most for embodied, active-mapping and SLAM ideas; graphics venues (SIGGRAPH, TOG) for
   rendering. Say which apply. "Open in the vault" means "not found here", not "novel". Give
   the exact follow-up searches:
   - 2-4 arXiv / Google Scholar queries;
   - the older foundations the neighbours build on that are not in the vault (the "Works most
     built upon ... NOT in the vault" recipe with the neighbours' IDs), which the user should
     check directly.

   If WebSearch is available, run those queries yourself and report what you find, labelled
   as outside the vault and unverified against the paper.
8. **Checkpoint 3: next step.** Offer to:
   - **sharpen the idea**: read `show ID ... --sections why --max-chars 2000` (the open
     questions sit at the end of the section) across the
     neighbours and the wider topic, and point to open problems that several papers raise but
     none addresses, especially those next to the user's idea;
   - **draft the related work** for it (hand off to the related-work skill, with the neighbours
     found here as the starting set);
   - **save the result**.

   The result goes in chat by default. Ideas are private and the vault is pushed, so write
   `research_ideas/<slug>.md` only if the user asks for it, and say that the folder will be
   committed with the vault unless they keep it out.

## Notes

- Never call an idea novel. The strongest statement is "nothing in the vault does this; check
  these external sources".
- Never say a paper does something its note or OCR does not show. When the overlap rests on a
  detail the OCR does not settle, say so.
- If the user's description is too vague to search (no mechanism, only a goal), say so at
  checkpoint 1 and help them pin down the mechanism first. The search depends on it.
