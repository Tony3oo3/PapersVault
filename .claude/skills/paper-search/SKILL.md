---
name: paper-search
description: Find papers in the PapersVault on a topic, method, dataset or question ("find papers on X", "who builds on Y", "papers like CVPR20250100", "what compares against Z"). Uses vault.py keyword search and the citation tables, screens one-line cards, and reads only the most relevant notes.
---

# Paper search

Read `REFERENCE.md` in this skill's folder first (commands, schema, caveats). Run
`vault.py status` before anything else.

## Steps

1. **Turn the question into 3-5 queries in the field's own terms.** The notes are written in
   standard terminology, so translate the user's wording: "stop an image generator from
   producing an artist's style" becomes `"concept erasure"`, `unlearning AND diffusion`,
   `"style removal"`. Add filters only if the user gave them (`--venue`, `--year`, `--type`,
   `--new`). To restrict to a domain, AND a group into each query:
   `(abstain OR abstention) AND ("vision-language" OR multimodal OR MLLM OR VQA)`. Read
   "Writing queries" in the reference first (stemming, prefixes, precedence). Run them in one
   call: `vault.py search Q1 Q2 Q3 -k 40`, then read the `# N matches` lines: re-run without
   any query that is far broader than it should be (e.g. `answerability`, stemmed to
   `answer`, matches 2.7k papers); it drowns the precise ones.
2. **Screen the cards.** Drop the off-topic ones. If almost nothing is on topic, the
   vocabulary is wrong: read the titles of the few good hits for the terms the field uses and
   search again with those.
3. **Expand from the best 2-3 hits:**
   - `like ID` for papers citing the same works. This works for method subfields (papers
     sharing a lineage); for behaviours or properties that cut across architectures
     (abstention, calibration, robustness) it mostly returns papers sharing generic
     backbones and benchmarks. Check the printed shared works before trusting a result;
   - `citers WORK` for papers building on a key method the hits build on (a partial title
     lists the variants with counts; run it on each variant of the same work);
   - a new `search` with terms seen in the good hits that the first queries missed.
   Stop when a round adds no new *on-topic* papers (rounds always add new off-topic cards).
4. **Read the notes in two passes**: screen the plausible ones with
   `show ID ... --sections problem method --max-chars 600`, then read the final 10-20 in full
   (`--sections results` is long, read it only for the shortlist).
5. **Answer** with a grouped list: paper ID, venue and year, one line on what it does, one on
   why it is relevant to the question. Say how many distinct cards you screened across all
   calls and what was left out on purpose (e.g. "12 papers on safety filtering rather than
   erasure, skipped"). Closely related work from an adjacent setting (e.g. text-only LLM
   papers for a VLM question) goes in its own short list rather than being dropped silently.

## Notes

- Questions about counts ("how many papers...", "is X growing?") are trends: use the
  trend-report skill or `trend` / `sql`, never a count of the cards you read.
- A paper with fewer than 3 citations recorded makes `like` unreliable (it says so): fall back
  to `search` on its key terms.
- Broad questions about a mechanism that cuts across subfields ("methods where the model
  decides per input how much compute to spend") need many phrasings and get noisy; tell the
  user when recall is likely incomplete rather than presenting the list as exhaustive.
