# PapersVault reference (shared by the paper-search, trend-report, related-work, topic-primer and novelty-check skills)

## Running vault.py

Run from the vault root with a Python that has PyYAML. On Leonardo that is the
PaperMiner venv: `../.venv/bin/python vault.py ...`. If it is not clear which
interpreter to use, ask the user; do not try interpreters until one works.

Start every task with `vault.py status`. Exit 1 means stale: run `vault.py build`
(incremental, seconds to minutes; the first build takes several minutes) and say so.
Options such as `--db` go after the subcommand: `vault.py search ... --db other.db`.

## What the vault is

One note per paper, `{CONF}{YEAR}/papers/{paper_id}.md`, written by Qwen3.8-27B from
the OCR of the paper: CVPR, ICCV, ECCV, ICLR, ICML, NeurIPS from 2024 on. Older work
and other venues appear only as cited titles in `builds_on` / `compares_to`.
The notes are summaries, not the papers: treat them as reliable by default, and go to the
paper itself (its OCR, see "Reading the paper itself") when a detail matters or the user asks
to verify.

Reading costs, cheapest first; go deeper only for papers that survive:
- card (title + key contribution, one line from `search`/`like`/`citers`): ~120 tokens
- full note (`show ID`): ~3k tokens; `show ID --sections problem method` for less
- one passage or table of the paper: `ocr ID --grep '<regex>'`: ~0.5-2k tokens
- the whole paper: `ocr ID`: 15-30k tokens (more with `--supplemental`)

## Commands

| Command | Use |
|---|---|
| `search Q [Q ...]` | keyword search (see "Writing queries"); several queries are fused by rank. Prints `# N matches` per query; shows `-k` (default 20) of the papers pooled from each query's top `--pool` (default 200) |
| `show ID [ID ...] [--sections ...] [--max-chars N]` | print notes; sections: problem io method results baselines prior why; `--max-chars 600` cuts each section for cheap screening |
| `like ID` / `like --works T1 T2 ...` | papers citing the same works as a paper, or as a list of works (a draft's references). Prints a score (rarer shared works weigh more) and the rarest shared works; ignores works cited by more than `--max-share` % (default 1) of all papers |
| `citers WORK [--kind builds_on|compares_to]` | papers that build on / compare to a work (paper ID or cited title). A partial title lists the matching cited titles (whole words) with counts: the same work often appears under 2-3 titles (arXiv renames), run `citers` on each |
| `trend --query Q | --cites WORK | --tag FIELD=VALUE` | share of papers per conference edition, in submission-deadline order, with a `prev` column (same venue's previous edition). `--within Q2`: share inside the papers matching Q2 instead of all papers (sub-topics of a topic). `--venue CVPR ECCV`: only those venues. `--sample N [--seed S]`: N random hits to check precision. Flags editions that look incomplete or are uncommitted |
| `sql "SELECT ..." [--ids-file F]` | read-only SQL (schema below); `:ids` in the query is replaced by the quoted IDs listed in F |
| `bib ID-or-title ...` / `bib --file F` | BibTeX from DBLP (see "BibTeX") |
| `ids Q [filters] [--within-ids F]` | paper IDs matching a query, one per line (to build an `--ids-file`); `--within-ids`: only those also in F (a sub-area inside a topic) |
| `lineage --query Q | --ids-file F [--nodes N --roots R]` | Mermaid graph of who builds on whom inside a topic (most built-upon papers with their ancestors and descendants, plus the older works outside the vault it builds on most); `--format json` for the numbers |
| `ocr ID [ID ...] [--grep RE] [--supplemental] [--path-only]` | the paper itself: its OCR markdown, image links made absolute (see "Reading the paper itself") |
| `cards SLUG` | fill the paper cards of a hand-built primer page, check its links, write `.bundle.html` (see the topic-primer skill) |
| `review [--topic SLUG] [--grade SLUG QID GRADE]` | spaced-repetition queue over the primers' `quiz.md` (see the quiz-me skill) |
| `cite draft.tex --bib F.bib` | replace `[ID]` / `[ID, ID]` / `[cited title]` markers with `\cite{...}` keys from a `bib` output |

`-k` defaults: 20 for search and like, 50 for citers.
Scratch files (`--ids-file` lists, intermediate output) go in `$TMPDIR` or your scratchpad, never
in the vault, except where a skill says so (a primer's `topic_ids.txt`).
Filters on search/like/citers: `--venue CVPR ICLR`, `--year 2025 2026`,
`--type benchmark dataset` (any of regular benchmark dataset position survey), `--task <substring of primary_task>`,
`--new` (papers that define a new task), `-k N`, `--long`.

## Writing queries (SQLite FTS5)

- Words are Porter-stemmed: `model` also matches `models`, so plain words are usually best.
  Stemming can over-merge (`answerability` becomes `answer`: thousands of matches) or fail to
  merge (`abstain` and `abstention` stay different: write `abstain OR abstention`).
- A prefix applies to the stem: `hallucin*` works, `hallucinat*` matches almost nothing.
  Avoid prefixes unless you need them.
- `"exact phrase"`; `a OR b`; `a AND b` (plain words are ANDed); `NOT`. AND binds tighter
  than OR: write `(a OR b) AND c`, never `a OR b AND c`.
- Hyphenated words are quoted automatically (`vision-language` -> `"vision-language"`). If a
  query is still invalid, the output says `# WARNING ... searched as plain words`: its
  meaning changed, so rewrite it.
- Restrict to the main claim for precision: `{title key_contribution}: ("gaussian splatting" OR 3dgs)`
  matches only papers *about* the topic, not those that merely use it as a baseline (the
  default also searches Problem, Method, tags and keywords). `title: word` for one column.
- Constrain to a domain by AND-ing a group: `(abstain OR abstention) AND ("vision-language" OR multimodal OR MLLM OR LVLM OR VQA)`.
- Always read the `# N matches` lines: drop or rewrite any query far broader than expected
  (hundreds or thousands of matches for something specific), or it floods the fused ranking.
- `NEAR(a b, 5)` is FTS5's proximity syntax (`NEAR/5` is not valid and degrades to plain words).

## Schema (vault.db)

- `papers(paper_id, edition, conference, year, title, authors, first_author, key_contribution,
  primary_task, paper_type, task_novelty, read_priority, code_available, code_url, pdf_url, note_path)`
- `tags(paper_id, field, value)`: fields `primary_task secondary_tasks method_family
  training_paradigm modality concerns novelty_type keywords datasets_trained_on
  datasets_evaluated_on datasets_introduced input output`
- `relations(paper_id, kind, title, ntitle, first_author, venue, evidence, vault_paper_id)`:
  `kind` is `builds_on` or `compares_to`; `ntitle` is the title lower-cased with every run of
  non-alphanumerics turned into one space (`"BOOT: Data-free ..."` -> `boot data free ...`);
  `vault_paper_id` is set when the cited work is itself in the vault, also when the citation's
  wording drifts from the vault title (acronym prefix, arXiv vs camera-ready title). Pass a
  paper ID to `citers`/`like --works`/`trend --cites` to cover the linked wordings. A title
  reworded anywhere (FisherRF's arXiv "... and Uncertainty Quantification for ..." vs "... and
  Mapping with ...") is linked only when the citations back it up -- same acronym, or same
  first author or venue -- and the change is one span of at most 2-3 words. So it still misses
  bigger rewrites and variants with no shared acronym cited as arXiv under a garbled author.
  For a key work, also run `citers "<short name>"` and fold in the variant titles it lists
- `editions(edition, conference, year, n_papers, fingerprint)`
- `fts`: full-text index, `fts.rowid = papers.id`

## Data caveats (read before counting anything)

- Never count by reading notes: every number comes from `trend` or `sql`.
- Tags are free-form LLM output, never normalized: `3d-gaussian-splatting` (1266),
  `3D Gaussian Splatting` (801), `gaussian-splatting` (477), `3DGS` (227) are one method.
  `--tag` matches one exact value (case-insensitive), so for named methods use `--query` or
  `--cites` instead; if you must use tags, list the variants first
  (`sql "SELECT value, count(*) FROM tags WHERE field = '...' AND value LIKE '%...%' GROUP BY 1"`).
- Citing the founding paper undercounts a topic as it matures: later papers build on its
  descendants instead (3DGS papers listing the original 3DGS paper in `builds_on` fell from
  95% to 69% between 2024 and 2026). Use `--cites` for when a topic took off; for its level
  later, use a `--query` restricted to title and contribution.
- Useless for ranking: `novelty_type` (empirical-study on ~98%), `read_priority` (~90% medium),
  `extraction_confidence`. Useful: `paper_type`, `task_novelty = 'new'`, `code_available`.
- Editions differ in size and topic mix: compare shares, not counts. The cleanest comparison
  is the same venue across years (the `prev` column: CVPR 24/25/26, ECCV 24/26, ICLR 24/25/26).
  Venues differ even within a family (ICML carries far less 3D vision than NeurIPS or ICLR),
  and ECCV/ICCV alternate years, so an interleaved row-by-row reading mixes venue effects
  into the trend. Order editions by submission deadline (as `trend` does), not by year: ICML
  2025 (deadline Jan 2025) predates NeurIPS 2025 (May 2025).
- Drop rows `trend` flags as INCOMPLETE (an edition still being summarized is not a random
  sample); treat "uncommitted" rows with caution.
- A keyword query's share is only as good as its precision: always run `trend --sample 20`,
  write down the inclusion rule *before* judging (e.g. "uses 3DGS as its representation" vs
  "mentions it"), and report the precision (strict and lenient if they differ).

## Useful SQL

Fastest-rising cited works between two editions (swap kind / editions as needed):
```sql
WITH c AS (SELECT r.ntitle, p.edition, count(DISTINCT r.paper_id) n FROM relations r
           JOIN papers p USING (paper_id) WHERE r.kind = 'builds_on'
           AND p.edition IN ('ICLR2025', 'ICLR2026') GROUP BY 1, 2)
SELECT c.ntitle,
  round(100.0 * sum(CASE WHEN c.edition = 'ICLR2025' THEN c.n END) / (SELECT n_papers FROM editions WHERE edition = 'ICLR2025'), 2) AS pct_before,
  round(100.0 * sum(CASE WHEN c.edition = 'ICLR2026' THEN c.n END) / (SELECT n_papers FROM editions WHERE edition = 'ICLR2026'), 2) AS pct_after
FROM c GROUP BY c.ntitle HAVING pct_after >= 0.3
ORDER BY coalesce(pct_after, 0) - coalesce(pct_before, 0) DESC
```

Works most built upon by a set of papers that are NOT in the vault (foundations to cite);
put the IDs in a file and run with `--ids-file`:
```sql
SELECT max(title) AS title, count(DISTINCT paper_id) AS n FROM relations
WHERE kind = 'builds_on' AND vault_paper_id IS NULL AND paper_id IN (:ids)
GROUP BY ntitle ORDER BY n DESC LIMIT 20
```

Rising cited works *within a topic*, pooled by phase and normalised by topic size
(e.g. what 3DGS papers build on in CVPR+ECCV 2024 vs 2026). Run the topic query once with
`search`/`sql` to get its IDs, or inline the FTS match as below:
```sql
WITH t AS (SELECT p.paper_id, CASE WHEN p.year = '2024' THEN 'before' ELSE 'after' END AS phase
           FROM fts JOIN papers p ON p.id = fts.rowid
           WHERE fts MATCH '{title key_contribution}: ("gaussian splatting" OR 3dgs)'
             AND p.conference IN ('CVPR', 'ECCV') AND p.year IN ('2024', '2026')),
     n AS (SELECT phase, count(*) AS n FROM t GROUP BY phase)
SELECT min(r.title) AS work,
  round(100.0 * count(DISTINCT CASE WHEN t.phase = 'before' THEN r.paper_id END) / (SELECT n FROM n WHERE phase = 'before'), 1) AS pct_before,
  round(100.0 * count(DISTINCT CASE WHEN t.phase = 'after' THEN r.paper_id END) / (SELECT n FROM n WHERE phase = 'after'), 1) AS pct_after
FROM relations r JOIN t USING (paper_id) WHERE r.kind = 'builds_on'
GROUP BY r.ntitle HAVING pct_before + pct_after >= 2 ORDER BY pct_after - pct_before DESC
```

Most influential papers in a set (canonical papers of a topic or sub-area): how many vault
papers build on or compare to each, with `--ids-file`:
```sql
SELECT p.paper_id, p.title, sum(r.kind = 'builds_on') AS built_on, sum(r.kind = 'compares_to') AS compared
FROM papers p JOIN (SELECT DISTINCT paper_id AS citer, kind, vault_paper_id FROM relations
                    WHERE vault_paper_id IN (:ids)) r ON r.vault_paper_id = p.paper_id
GROUP BY p.paper_id ORDER BY built_on + compared DESC LIMIT 20
```

Datasets a set of papers evaluates on, with spelling variants merged (`Mip-NeRF 360`,
`mipnerf360`, `mip-nerf 360` become one row). Synonyms are not merged (`GSO` / `Google Scanned
Objects`, `Blender` / `NeRF-Synthetic`): add them up by hand:
```sql
SELECT max(value) AS dataset, count(DISTINCT paper_id) AS papers FROM tags
WHERE +field = 'datasets_evaluated_on' AND paper_id IN (:ids)  -- '+' keeps the paper_id index
GROUP BY lower(replace(replace(replace(replace(value, '-', ''), ' ', ''), '_', ''), '&', 'and'))
ORDER BY papers DESC LIMIT 25
```

Most common baselines in a set:
```sql
SELECT max(title) AS baseline, count(DISTINCT paper_id) AS papers FROM relations
WHERE kind = 'compares_to' AND paper_id IN (:ids)
GROUP BY coalesce(vault_paper_id, ntitle) ORDER BY papers DESC LIMIT 25
```

Avoid correlated subqueries over `relations` (one subquery per row): use JOIN + GROUP BY.
`sql` stops a query after `--timeout` seconds (default 60).

Papers defining a new task, per edition:
```sql
SELECT edition, count(*) FROM papers WHERE task_novelty = 'new' GROUP BY 1
```

Most common baselines for a task (the de-facto comparison set):
```sql
SELECT min(r.title), count(DISTINCT r.paper_id) n FROM relations r JOIN papers p USING (paper_id)
WHERE r.kind = 'compares_to' AND p.primary_task LIKE '%depth-estimation%'
GROUP BY r.ntitle ORDER BY n DESC LIMIT 20
```

## BibTeX

`bib` looks every reference up in DBLP, vault papers included, through DBLP's SPARQL
endpoint (the dblp.org website and search API block scripted clients). Each entry is
preceded by `% vault.py ref: <ID or title>`, which `cite` uses to swap markers for DBLP keys.
It prefers the proceedings version over arXiv; for a vault paper found only on arXiv it also
searches the proceedings by venue, year and first author (camera-ready titles often differ).
Everything doubtful is written anyway but marked `% vault.py: CHECK -- <reason>` and listed on
stderr as `CHECK` lines: always pass them to the user. Reasons: no DBLP match (placeholder
with a `vault:` or `unresolved:` key), first author differs from the note (the note can be
wrong), proceedings title differs, venue or year mismatch, DBLP unavailable (exit code 2:
re-run later). Each new reference takes ~3-5 s (DBLP is rate-limited); lookups are cached in
`dblp_cache.db`, so re-runs are instant. `--refresh` ignores the cache.

## Reading the paper itself (OCR)

Every paper's full text is on disk as GLM-OCR markdown, one squashfs image per conference in
`../papers_sqsh/{CONF}_{YEAR}.sqsh`. `vault.py ocr ID` finds the paper's folder (through the
`{CONF}{YEAR}/ids.json` map loaded by `build`) and mounts the conference's image read-only on
first use. It is cheaper than fetching the PDF and needs no internet.
- `ocr ID --grep 'PSNR|Table 2'`: only the blocks matching a case-insensitive regex, each with
  the section heading it sits under. Tables are HTML `<table>` blocks, equations LaTeX. Use
  this to check one number, one claim, or one definition. `--context N` also prints the N
  blocks after each match: algorithms, equations and figure captions are split across blocks,
  so `--grep 'Algorithm 1' --context 15` gets the whole algorithm.
- `ocr ID`: the whole paper. Use it for the method of a cornerstone paper, or when a detail
  decides something (novelty, a primer's core section).
- `--supplemental`: the supplemental material too (when the paper has one, the output says so).
- `--path-only`: the .md paths only. Figures are the `imgs/*.jpg` next to them, and the image
  links in the printed markdown are absolute, so a figure can be opened with Read.

OCR quality is high but not perfect: a garbled table cell or symbol is an OCR error, not the
paper's. When a number is decisive and the OCR looks off, check the PDF via `pdf_url`.

Where things live, and what to change if they move:
- images: `$PAPERMINER_SQSH_DIR` (default `../papers_sqsh`);
- mounts: `$VAULT_OCR_MOUNTS` (default `$TMPDIR/paperminer-ocr-$USER/{CONF}_{YEAR}`);
- mount command: `$VAULT_SQSH_MOUNT` (default `micromamba run -n sqsh squashfuse_ll`, i.e. the
  `sqsh` env on Leonardo; the command must daemonize);
- fallback when FUSE fails: only the needed folders are extracted with `$VAULT_SQSH_EXTRACT`
  (default `micromamba run -n sqsh unsquashfs`).

A mount whose daemon died (login nodes cap CPU time per process) is detected and remounted
automatically. To unmount: `fusermount -u <mount>`. `vault.py status` says which conferences
have an image. Without one, fall back to the PDF through `pdf_url`.

## Verification (only when the user asks)

To verify a claim or a number, read the specific passage or table in the OCR
(`ocr ID --grep ...`), or in the PDF via `pdf_url` when no OCR image is available. Say which
claims were checked against the paper and which come from the note only.

## Citing

Every paper mentioned in an answer carries its paper ID (`CVPR20250100`), so the user can
open the note. Never state something about a paper that its note does not support.
