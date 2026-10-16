---
name: related-work
description: Draft the related-work section for the user's paper from the PapersVault, with BibTeX from DBLP. Input is the user's draft (PDF, LaTeX or text) or a description of the work. Finds neighbouring papers by shared citations and keywords, agrees the themes with the user, then writes cited paragraphs.
---

# Related work

Read `../paper-search/REFERENCE.md` first. Run `vault.py status`. If
`research_topics/_me.md` exists, read its "Current projects": the draft is often one of them.

## Steps

1. **Read the user's draft** and write down, as the pipeline does for vault papers: the
   primary task; method family; datasets; the methods the work builds on (`builds_on`); the
   baselines it compares against (`compares_to`); the works its own related-work section or
   introduction already cites; 5-10 key technical terms. Ask the user for anything the draft
   does not settle (e.g. which baselines are final). If the draft itself is a vault paper
   (camera-ready, arXiv), note its ID and exclude it from every result.
2. **Gather candidates** (aim for a few hundred cards):
   - `like --works "<title>" "<title>" ... -k 80` with the *specific* works the draft cites:
     its baselines and the related work it already discusses. The command prints how many
     vault papers cite each work and ignores ubiquitous ones (DDPM, ResNet, CLIP); if most of
     what is left is generic for the field, the result is noise: rely on the other routes;
   - `search` with the key terms, 3-5 queries, `-k 60`;
   - `citers "<full title or paper ID>"` for direct follow-ups of a specific method the draft
     builds on (short names like "BOOT" also match unrelated titles; skip works with
     hundreds of citers, the list is by year, not relevance);
   - optionally `--task` / dataset queries for papers on the same task.
   When the draft has no direct baselines (empty `compares_to`, or a new task), the themes
   come from keyword search on the problem and from adjacent fields: say so in step 5.
3. **Screen to ~40-80 papers** from the cards, then read their notes
   (`show ID ... --sections problem method prior --max-chars 800`). With more than ~20 notes,
   split them across subagents that each return a short digest per paper (ID, title, what it
   does, how it relates to the draft). Give each subagent its own output file, or have it
   read `show` output directly: subagents writing to one shared file corrupt each other's
   notes silently.
4. **Add the foundations outside the vault**, per theme: put the theme's paper IDs in a file
   and run the "Works most built upon ... NOT in the vault" recipe with
   `sql "... paper_id IN (:ids) ..." --ids-file theme1.txt`. Skip works that are generic for
   the whole field (DDPM, LDM, Adam); keep the ones specific to the theme. The vault only
   covers 2024 onwards, so these are usually the older must-cite works.
5. **Checkpoint with the user before writing.** Propose 3-5 themes (one paragraph each) with
   the papers under each and a one-line angle for how the draft differs. The user decides the
   positioning: adjust until they agree.
6. **Write the paragraphs.** Every claim about a paper carries its marker `[CVPR20250100]`
   (several: `[CVPR20250100, ICLR20240047]`; for works outside the vault, the cited title).
   Tie each per-paper claim to something its note says; keep broad framing sentences
   ("distillation for diffusion has mostly targeted sampling speed") to what the papers you
   read collectively show, and soften them otherwise. End each paragraph with how the user's
   work differs from that line of work.
7. **BibTeX:** put every marker in `refs.txt`, one per line (duplicates are dropped), run
   `vault.py bib --file refs.txt > related.bib`, then
   `vault.py cite draft.tex --bib related.bib > draft_cited.tex` to turn the markers into
   `\cite{...}` keys. `bib` takes ~3-5 s per new reference (cached afterwards).
8. **Deliver** the LaTeX paragraphs and the `.bib`, plus: which claims are from the notes only
   (all of them, unless the user asked for verification), and every `CHECK` line `bib`
   printed: placeholders DBLP could not match, an author list that differs from the note, a
   proceedings title that differs from the vault's, a venue or year mismatch, or "DBLP
   unavailable" (then re-run `bib` later: finished lookups are cached).

## Verification (only when asked)

The notes are summaries. When the user asks to verify (typically before submission), check
each cited claim and every number against the paper itself, with `vault.py ocr ID --grep '...'`
(the PDF via `pdf_url` only where no OCR image exists), and report what was checked, what was
corrected and what could not be confirmed.
