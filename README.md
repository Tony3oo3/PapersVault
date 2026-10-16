# PapersVault

Obsidian-style vault of LLM-summarized conference papers, one directory per
conference (`{CONF}{YEAR}/papers/*.md`) plus a flattened `index.json` per
conference for search.

## Figures are not in this repo

Notes link their figures as `../imgs/{paper_id}/{file}.webp`, but `imgs/` is
gitignored: ~19k images would be over 2 GB of binaries that are fully derived
from the OCR output. They live in a private Google Drive folder instead.

To fetch them for one conference:

```bash
rclone copy unitn_drive:PaperMiner_imgs/NEURIPS2025 ./NEURIPS2025/imgs
```

Or mount on demand, so nothing is stored locally until a note is opened:

```bash
rclone mount unitn_drive:PaperMiner_imgs/NEURIPS2025 ./NEURIPS2025/imgs \
    --vfs-cache-mode full --daemon
```

Without either, the notes read fine; the figures just show as broken links.

## Search database

`vault.py` builds `vault.db`, a local SQLite database over all the notes, for
keyword search, citation lookups and counts across conferences. It is built
only from the notes, so a clone of this repo is all it needs: no PDFs, OCR
output or GPU.

Requirements: Python 3.9+ with PyYAML (`pip install pyyaml`), and an SQLite
with FTS5, which most Python builds include (`vault.py` checks and says so if
not).

```bash
python vault.py build          # create, or update after a git pull
python vault.py build --full   # drop it and rebuild from scratch
python vault.py status         # is vault.db current? exit 0 if yes, 1 if not
```

The first build reads every note: about 4 minutes and ~700 MB for ~45k
papers. Later builds are incremental: a conference is re-indexed only if one
of its notes was added, removed or modified, so after a `git pull` that adds
one conference it takes seconds plus that conference.

How changes are detected: for each conference the database stores a
fingerprint. If the conference's `papers/` folder is clean in git, that is
git's tree hash of the folder, which changes only when note content does, so
checking it is instant and a fresh clone or branch switch does not cause a
re-index. If the folder has uncommitted or untracked notes (the pipeline
before it commits, or edits from Obsidian), it falls back to a hash of every
note's name, size and modification time. `status` also prints the commit the
database was built at next to the current `HEAD`. It exits 1 when anything
is stale, so a script can run `python vault.py status || python vault.py build`.

`vault.db` is gitignored on purpose. It is a derived copy of the notes, over
GitHub's 100 MB file limit, and every rebuild would add another full copy to
the history. Rebuild it instead of copying it around.

What it contains:

| Table | Content |
|-------|---------|
| `papers` | one row per note: id, conference, year, title, authors, key contribution, primary task, paper type, task novelty, code link, note path, and `pdf_url` (the URL the PDF was downloaded from; null only for papers since withdrawn from the proceedings) |
| `fts` | full-text index (SQLite FTS5, Porter stemming) over title, key contribution, Problem, Method, tags and keywords; its rowid is `papers.id` |
| `tags` | every list-valued classification field (tasks, method family, datasets, keywords, ...), one row per value |
| `relations` | every `builds_on` / `compares_to` entry; `vault_paper_id` is set when the cited title matches a paper in the vault |
| `editions` | one row per conference, with the fingerprint used for incremental builds |
| `meta` | schema version, build time, and the git commit the database was built at |

## Querying it

Every query command prints compact output (one two-line "card" per paper) so
many candidates can be screened quickly; `python vault.py <command> -h` lists
the options.

```bash
python vault.py search '"concept erasure"' 'unlearning AND diffusion' --venue CVPR ICLR
python vault.py show CVPR20250100 --sections problem method
python vault.py like CVPR20262812                      # papers citing the same works
python vault.py like --works "Consistency Models" "Denoising diffusion probabilistic models"
python vault.py citers "flow matching for generative modeling" --kind builds_on
python vault.py trend --cites "flow matching for generative modeling" --sample 20
python vault.py sql "SELECT edition, count(*) FROM papers WHERE task_novelty = 'new' GROUP BY 1"
python vault.py bib CVPR20250100 "Denoising diffusion probabilistic models" > refs.bib
python vault.py cite draft.tex --bib refs.bib > draft_cited.tex   # [ID] markers -> \cite{...}
```

- `search` takes SQLite FTS5 syntax (`"phrase"`, `OR`, `AND`, `NOT`, `prefix*`);
  several queries are fused into one ranking.
- `trend` prints the share of papers per conference in submission-deadline order,
  marking vision and ML venues, which should be compared separately.
- `bib` looks every reference up in DBLP, vault papers included, through DBLP's
  SPARQL endpoint (dblp.org's own API blocks scripted clients). It needs
  internet, is rate-limited by DBLP, and caches results
  in `dblp_cache.db` (gitignored), so a new reference takes a few seconds and a
  repeated one none. Anything doubtful (no match, an author list or proceedings
  title that differs from the note, an arXiv-only hit for a proceedings paper,
  DBLP unreachable) is still written but marked `% vault.py: CHECK -- ...` and
  listed on stderr.
- Citations are linked to vault papers by title, tolerating the usual drift
  between how a paper is cited and its vault title (an acronym prefix, an arXiv
  title vs the camera-ready one), so `citers CVPR20250100` covers every wording.

## Reading the papers themselves

Each conference's OCR (GLM-OCR markdown + figures) is a squashfs image in the
PaperMiner repo's `papers_sqsh/`. `{CONF}{YEAR}/ids.json` (committed, copied
from the pipeline's state) maps paper IDs to the folders inside it, so:

```bash
python vault.py ocr CVPR20240382 --grep 'Deepglobe'   # matching paragraphs/tables only
python vault.py ocr CVPR20240382 --supplemental        # the whole paper + supplemental
```

mounts the conference's image read-only on first use (`squashfuse_ll` from the
`sqsh` micromamba env; see `.claude/skills/paper-search/REFERENCE.md` for the
environment variables) and prints the markdown. `status` lists which
conferences have an image.

## Research topic primers

`research_topics/<topic>/` holds a primer on one topic, written by the
`topic-primer` skill: the field explained from first principles, grounded in
the notes and papers, as a hand-built web page (`index.html`) with diagrams,
interactive figures, paper figures, a lineage graph, trend charts and a reading
path. Next to it: `primer.md` (an Obsidian companion with the reading path and
the primer's state), `quiz.md` (questions for the `quiz-me` skill),
`topic_ids.txt` and `figs/`. Primers are updated in place as new conferences
land: each update is a dated entry in the page's Updates section, and
`vault.py status` lists primers that miss a conference.

The pages share `research_topics/_kit/` (style, paper cards, checkboxes,
charts). After editing a page:

```bash
python vault.py cards 3d-gaussian-splatting   # refresh its paper cards, check links, write .bundle.html
```

Open `index.html` in a browser from a clone (it loads MathJax, Mermaid and fonts
from a CDN), or the private claude.ai Artifact the skill publishes from
`.bundle.html` (the page with the kit inlined; gitignored). The Artifact also
has a **tutor**: select a passage and press "Ask about this", or use the "Ask"
button next to a heading, and Claude explains it in a side panel. It uses your
own Claude account, and the page asks once for permission. It sees the section
you are reading, the paper cards and `_me.md`, which is embedded in the
published copy only. It cannot search the vault or read the papers' OCR; for
that, ask in Claude Code in this folder. Every chat is saved privately in the
Artifact's database: the tutor's **Archive** reopens, exports (Markdown with
`[[ID]]` links) or deletes them. The skills read them too, through
`ArtifactData` on `data/users/me`, to see what you found hard.

`research_topics/_me.md` describes the reader (background, projects, concepts
known) so primers skip what you know; `_reviews.json` is the quiz schedule
(`python vault.py review` lists what is due).

## Claude Code skills

`.claude/skills/` holds the skills Claude Code loads when started in this
folder:

| Skill | For |
|---|---|
| `paper-search` | find papers on a topic, method or dataset |
| `trend-report` | how a topic moves across conferences |
| `related-work` | draft a related-work section with BibTeX |
| `topic-primer` | learn a topic: a primer page, kept up to date |
| `novelty-check` | is my idea new? (interactive) |
| `quiz-me` | spaced-repetition quiz on the primers |

They drive `vault.py` and share `.claude/skills/paper-search/REFERENCE.md`,
which holds the schema, the data caveats (tags are not normalized, compare
vision and ML venues separately, never count by reading) and useful SQL.

## Provenance

Generated by the `paper_miner` pipeline. Notes are written once and validated
before landing, so prefer regenerating over hand-editing frontmatter.
