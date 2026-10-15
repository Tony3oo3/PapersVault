#!/usr/bin/env python3
"""vault.py -- local search database over the PapersVault notes.

    python vault.py build            # create or update vault.db next to this file
    python vault.py build --full     # drop everything and rebuild from scratch
    python vault.py status           # is vault.db current? exit 0 if so, 1 if not

The database is derived entirely from the notes ({CONF}{YEAR}/papers/*.md), so
it is never committed: rebuild it after every `git pull`. `build` is
incremental -- a conference is re-indexed only when one of its note files was
added, removed or modified since the last build.

Change detection: a conference whose papers/ folder is clean in git is
fingerprinted by its git tree hash (content-based, instant). One with
uncommitted or untracked notes -- the pipeline before it commits, or edits
from Obsidian -- falls back to a hash of every note's name, size and mtime.

Needs Python 3.9+ with PyYAML, and an SQLite with FTS5 (most builds have it).
"""

import argparse
import glob
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import yaml

try:  # the C loader is ~10x faster; fall back to pure Python if absent
    _Loader = yaml.CSafeLoader
except AttributeError:
    _Loader = yaml.SafeLoader

VAULT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(VAULT, "vault.db")
SCHEMA_VERSION = "1"
LINK_VERSION = "3"  # bump when link_citations() changes: the next build re-links everything

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
-- one row per conference edition, with the fingerprint used for incremental builds
CREATE TABLE editions(edition TEXT PRIMARY KEY, conference TEXT, year TEXT,
                      n_papers INTEGER, fingerprint TEXT);
CREATE TABLE papers(
    id INTEGER PRIMARY KEY,          -- also the rowid of the fts table
    paper_id TEXT UNIQUE, edition TEXT, conference TEXT, year TEXT,
    title TEXT, ntitle TEXT, authors TEXT, first_author TEXT,
    key_contribution TEXT, primary_task TEXT, paper_type TEXT,
    task_novelty TEXT, read_priority TEXT, code_available INTEGER, code_url TEXT,
    pdf_url TEXT, note_path TEXT);
-- every list-valued classification field, one row per (paper, field, value)
CREATE TABLE tags(paper_id TEXT, field TEXT, value TEXT);
-- builds_on / compares_to entries; vault_paper_id is set when the cited
-- title matches a paper in the vault
CREATE TABLE relations(paper_id TEXT, kind TEXT, title TEXT, ntitle TEXT,
                       first_author TEXT, venue TEXT, evidence TEXT,
                       vault_paper_id TEXT);
CREATE VIRTUAL TABLE fts USING fts5(
    title, key_contribution, problem, method, tags, keywords,
    tokenize='porter unicode61');
CREATE INDEX papers_edition ON papers(edition);
CREATE INDEX papers_ntitle ON papers(ntitle);
CREATE INDEX tags_value ON tags(field, value);
CREATE INDEX tags_paper ON tags(paper_id);
CREATE INDEX rel_ntitle ON relations(ntitle);
CREATE INDEX rel_paper ON relations(paper_id);
"""

TAG_FIELDS = ("secondary_tasks", "method_family", "training_paradigm", "modality",
              "concerns", "novelty_type", "keywords", "datasets_trained_on",
              "datasets_evaluated_on", "datasets_introduced", "input", "output")


def norm_title(t):
    """Lower-cased alphanumerics only: how cited titles are matched to papers."""
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def as_list(v):
    return v if isinstance(v, list) else []


def edition_dirs():
    return sorted(d for d in os.listdir(VAULT)
                  if os.path.isdir(os.path.join(VAULT, d, "papers")))


def note_files(edition):
    return sorted(glob.glob(os.path.join(VAULT, edition, "papers", "*.md")))


def git(*args):
    """stdout of a git command run in the vault, or None if git or the repo is unavailable."""
    try:
        r = subprocess.run(["git", "-C", VAULT, *args], capture_output=True, text=True)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def git_head():
    head = git("rev-parse", "HEAD")
    return head.strip() if head else None


def fingerprints(editions):
    """{edition: fingerprint} -- 'git:<tree hash>' when the edition's papers/
    folder is clean in git, else 'mtime:<hash of every note's name/size/mtime>'."""
    trees, dirty = {}, set(editions)
    top = git("rev-parse", "--show-toplevel")
    if top and os.path.realpath(top.strip()) == os.path.realpath(VAULT):
        paths = [f"{e}/papers" for e in editions]
        status = git("status", "--porcelain", "-z", "--untracked-files=normal", "--", *paths)
        tree = git("ls-tree", "HEAD", "--", *paths)
        if status is not None and tree is not None:
            dirty = set()
            for entry in filter(None, status.split("\0")):
                # "XY path" entries; a rename's source path follows without the prefix
                path = entry[3:] if len(entry) > 3 and entry[2] == " " else entry
                dirty.add(path.split("/", 1)[0])
            for line in tree.splitlines():  # "040000 tree <hash>\t<edition>/papers"
                meta, path = line.split("\t", 1)
                trees[path.split("/", 1)[0]] = meta.split()[2]
    fps = {}
    for e in editions:
        if e not in dirty and e in trees:
            fps[e] = "git:" + trees[e]
        else:
            h = hashlib.sha1()
            for f in note_files(e):
                st = os.stat(f)
                h.update(f"{os.path.basename(f)}:{st.st_size}:{st.st_mtime_ns}\n".encode())
            fps[e] = "mtime:" + h.hexdigest()
    return fps


def parse_note(path):
    """Return everything the database needs from one note, or None if unparseable."""
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return None
    head, body = text[4:].split("\n---\n", 1)
    try:
        fm = yaml.load(head, Loader=_Loader) or {}
    except yaml.YAMLError:
        return None
    if not fm.get("paper_id"):
        return None
    sections = {m.group(1).strip(): re.sub(r"!\[[^\]]*\]\([^)]*\)", "", m.group(2)).strip()
                for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, re.S | re.M)}
    rels = []
    for kind in ("builds_on", "compares_to"):
        for e in as_list(fm.get(kind)):
            if isinstance(e, dict) and e.get("title"):
                rels.append((kind, str(e["title"]), norm_title(e["title"]),
                             str(e.get("first_author") or ""), str(e.get("venue") or ""),
                             str(e.get("evidence") or "")))
    tags = [(f, str(v)) for f in TAG_FIELDS for v in as_list(fm.get(f)) if v not in (None, "")]
    return {"fm": fm, "sections": sections, "rels": rels, "tags": tags,
            "note_path": os.path.relpath(path, VAULT)}


def insert_edition(db, edition, parsed):
    conf = re.match(r"[A-Z]+", edition).group(0)
    year = edition[len(conf):]
    n = 0
    for p in parsed:
        if p is None:
            continue
        fm, s = p["fm"], p["sections"]
        code = fm.get("code_available")
        cur = db.execute(
            "INSERT INTO papers(paper_id, edition, conference, year, title, ntitle, authors,"
            " first_author, key_contribution, primary_task, paper_type, task_novelty,"
            " read_priority, code_available, code_url, pdf_url, note_path)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fm["paper_id"], edition, conf, year, str(fm.get("title") or ""),
             norm_title(fm.get("title")), "; ".join(map(str, as_list(fm.get("authors")))),
             str(fm.get("first_author") or ""), str(fm.get("key_contribution") or ""),
             str(fm.get("primary_task") or ""), str(fm.get("paper_type") or ""),
             str(fm.get("task_novelty") or ""), str(fm.get("read_priority") or ""),
             None if code is None else int(bool(code)), fm.get("code_url"),
             fm.get("pdf_url"), p["note_path"]))
        tag_text = " ".join([str(fm.get("primary_task") or "")] +
                            [v for f, v in p["tags"] if f in TAG_FIELDS[:5]]).replace("-", " ")
        keywords = " ; ".join(v for f, v in p["tags"] if f == "keywords")
        db.execute("INSERT INTO fts(rowid, title, key_contribution, problem, method, tags, keywords)"
                   " VALUES (?,?,?,?,?,?,?)",
                   (cur.lastrowid, str(fm.get("title") or ""), str(fm.get("key_contribution") or ""),
                    s.get("Problem", ""), s.get("Method", ""), tag_text, keywords))
        if fm.get("primary_task"):
            db.execute("INSERT INTO tags VALUES (?,?,?)", (fm["paper_id"], "primary_task", str(fm["primary_task"])))
        db.executemany("INSERT INTO tags VALUES (?,?,?)", [(fm["paper_id"], f, v) for f, v in p["tags"]])
        db.executemany("INSERT INTO relations VALUES (?,?,?,?,?,?,?,NULL)",
                       [(fm["paper_id"],) + r for r in p["rels"]])
        n += 1
    return n


def delete_edition(db, edition):
    db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM papers WHERE edition = ?)", (edition,))
    db.execute("DELETE FROM tags WHERE paper_id IN (SELECT paper_id FROM papers WHERE edition = ?)", (edition,))
    db.execute("DELETE FROM relations WHERE paper_id IN (SELECT paper_id FROM papers WHERE edition = ?)", (edition,))
    db.execute("DELETE FROM papers WHERE edition = ?", (edition,))
    db.execute("DELETE FROM editions WHERE edition = ?", (edition,))


def open_db(path, full):
    if full and os.path.exists(path):
        os.remove(path)
    fresh = not os.path.exists(path)
    db = sqlite3.connect(path)
    if fresh:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
        db.commit()
    elif db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != SCHEMA_VERSION:
        db.close()
        print("vault.db has an older schema -- rebuilding from scratch", file=sys.stderr)
        return open_db(path, True)
    return db


def cmd_build(args):
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    except sqlite3.OperationalError:
        sys.exit("ERROR: this Python's SQLite has no FTS5 support; use another Python build.")
    t0 = time.time()
    db = open_db(args.db, args.full)
    # No fsync per commit: on network filesystems (Lustre) it makes a build many
    # times slower. The rollback journal still covers a crashed or killed build;
    # only an OS crash mid-build could damage the file (fix: build --full).
    db.execute("PRAGMA synchronous = OFF")
    db.execute("PRAGMA cache_size = -1000000")  # ~1 GB page cache: fewer small reads over the network
    known = dict(db.execute("SELECT edition, fingerprint FROM editions"))
    present = edition_dirs()
    fps = fingerprints(present)
    # A build killed between indexing and the citation linking below would
    # otherwise leave links missing with every edition already "up to date".
    meta = dict(db.execute("SELECT key, value FROM meta"))
    changed = meta.get("build_complete") == "0" or meta.get("link_version") != LINK_VERSION
    db.execute("INSERT OR REPLACE INTO meta VALUES ('build_complete', '0')")
    db.commit()
    for edition in sorted(set(known) - set(present)):
        print(f"{edition}: no longer in the vault, removing")
        delete_edition(db, edition)
        changed = True
    with ProcessPoolExecutor(args.workers) as pool:
        for edition in present:
            fp = fps[edition]
            if known.get(edition) == fp:
                print(f"{edition}: up to date")
                continue
            t = time.time()
            files = note_files(edition)
            parsed = list(pool.map(parse_note, files, chunksize=64))
            delete_edition(db, edition)
            n = insert_edition(db, edition, parsed)
            conf = re.match(r"[A-Z]+", edition).group(0)
            db.execute("INSERT INTO editions VALUES (?,?,?,?,?)", (edition, conf, edition[len(conf):], n, fp))
            db.commit()
            bad = len(files) - n
            print(f"{edition}: indexed {n} notes in {time.time() - t:.0f}s"
                  + (f" ({bad} unparseable, skipped)" if bad else ""))
            changed = True
    if changed:
        # Redone in full: a new edition can resolve citations made by older ones.
        fuzzy = link_citations(db)
        print(f"linked citations to vault papers ({fuzzy} cited titles matched despite wording drift)")
        db.execute("INSERT INTO fts(fts) VALUES ('optimize')")
    db.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                   [("build_complete", "1"), ("link_version", LINK_VERSION), ("git_head", git_head() or ""),
                    ("built_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))])
    db.commit()
    # Re-indexing leaves the deleted rows' pages free; compact once they are a
    # sizeable share of the file rather than after every small update.
    free, total = (db.execute(f"PRAGMA {p}").fetchone()[0] for p in ("freelist_count", "page_count"))
    if total and free / total > 0.25:
        print(f"compacting ({100 * free / total:.0f}% of the file is free space)")
        db.execute("VACUUM")
    n_papers = db.execute("SELECT count(*) FROM papers").fetchone()[0]
    n_linked = db.execute("SELECT count(*) FROM relations WHERE vault_paper_id IS NOT NULL").fetchone()[0]
    db.close()
    print(f"vault.db: {n_papers} papers, {n_linked} citations linked to vault papers, "
          f"{os.path.getsize(args.db) / 1e6:.0f} MB, {time.time() - t0:.0f}s")


def _title_core(title):
    """Title without a short leading "ACRONYM:" and without any non-alphanumerics."""
    t = str(title or "")
    head, sep, rest = t.partition(":")
    if sep and len(head.split()) <= 4 and len(rest.split()) >= 3:
        t = rest
    return re.sub(r"[^a-z0-9]", "", t.lower())


def link_citations(db):
    """Set relations.vault_paper_id: exact normalised-title match first, then a fuzzy pass
    for the usual drift between how a paper is cited and its vault title -- an acronym prefix
    ("BOOT: ..."), an arXiv title vs the proceedings title differing by a word, "Data-free"
    vs "Datafree". Returns how many cited titles only the fuzzy pass linked."""
    import difflib
    # Matching is done in memory and only changed rows are written: row-by-row
    # UPDATEs with an index lookup each are very slow on network filesystems.
    exact, by_prefix = {}, {}
    for pid, ntitle, title in db.execute("SELECT paper_id, ntitle, title FROM papers"):
        exact.setdefault(ntitle, pid)
        c = _title_core(title)
        if len(c) >= 20:
            by_prefix.setdefault(c[:16], []).append((pid, c))
    target, fuzzy = {}, 0
    current = {}
    for ntitle, title, linked in db.execute("SELECT ntitle, min(title), max(vault_paper_id) FROM relations"
                                            " GROUP BY ntitle").fetchall():
        current[ntitle] = linked
        if ntitle in exact:
            target[ntitle] = exact[ntitle]
            continue
        c = _title_core(title)
        if len(c) < 20:
            continue
        best = None
        for pid, pc in by_prefix.get(c[:16], ()):
            r = difflib.SequenceMatcher(None, c, pc).ratio()
            # short titles differ by one decisive word ("... are blind" / "... are biased")
            if r >= (0.9 if len(c) >= 40 else 0.96) and (best is None or r > best[0]):
                best = (r, pid)
        if best:
            target[ntitle] = best[1]
            fuzzy += 1
    changes = [(target.get(nt), nt) for nt, linked in current.items() if target.get(nt) != linked]
    db.executemany("UPDATE relations SET vault_paper_id = ? WHERE ntitle = ?", changes)
    return fuzzy


def cmd_status(args):
    """Report whether vault.db matches the notes; exit 0 if current, 1 if not."""
    if not os.path.exists(args.db):
        print(f"no database at {args.db} -- run: python vault.py build")
        sys.exit(1)
    db = sqlite3.connect(args.db)
    meta = dict(db.execute("SELECT key, value FROM meta"))
    known = {e: (fp, n) for e, fp, n in db.execute("SELECT edition, fingerprint, n_papers FROM editions")}
    db.close()
    if meta.get("schema_version") != SCHEMA_VERSION:
        print("vault.db has an older schema -- run: python vault.py build")
        sys.exit(1)
    present = edition_dirs()
    fps = fingerprints(present)
    stale = []
    for e in present:
        if e not in known:
            stale.append(f"{e}: not indexed yet")
        elif known[e][0] != fps[e]:
            why = "uncommitted or untracked notes" if fps[e].startswith("mtime:") else "notes changed in git"
            stale.append(f"{e}: changed ({why})")
    stale += [f"{e}: indexed but no longer in the vault" for e in sorted(set(known) - set(present))]

    built, head = meta.get("git_head") or None, git_head()
    print(f"built {meta.get('built_at', '?')} at commit {(built or 'n/a')[:10]}"
          f"; vault HEAD is {(head or 'n/a')[:10]}")
    if stale:
        print("out of date -- run: python vault.py build")
        for s in stale:
            print(f"  {s}")
        sys.exit(1)
    print(f"up to date: {sum(n for _, n in known.values())} papers in {len(known)} conferences")


# ---------------------------------------------------------------------------
# Query commands. Output is deliberately compact: one "card" line per paper,
# so an LLM can screen many candidates without reading whole notes.
# ---------------------------------------------------------------------------

# Approximate submission deadline of each venue relative to its conference year
# (years offset, month). Only used to ORDER editions in time: papers reflect the
# field as of the deadline, not the conference date.
DEADLINES = {"ICLR": (-1, 9), "CVPR": (-1, 11), "WACV": (-1, 7), "ICML": (0, 1),
             "ECCV": (0, 3), "ICCV": (0, 3), "NEURIPS": (0, 5)}
VISION = {"CVPR", "ICCV", "ECCV", "WACV"}
PAPER_ID = re.compile(r"^[A-Z]+\d{8}$")
BM25 = "bm25(fts, 5.0, 3.0, 2.0, 1.0, 2.0, 2.0)"  # title, contribution, problem, method, tags, keywords


def connect(path):
    if not os.path.exists(path):
        sys.exit(f"no database at {path} -- run: python vault.py build")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def deadline(conf, year):
    dy, month = DEADLINES.get(conf, (0, 6))
    return f"{int(year) + dy:04d}-{month:02d}"


def card(row, long=False):
    """row = (paper_id, conference, year, title, key_contribution)."""
    pid, conf, year, title, contrib = row
    contrib = contrib if long or len(contrib) <= 220 else contrib[:217].rstrip() + "..."
    return f"{pid}  {conf}'{str(year)[2:]}  {title}\n    {contrib}"


FTS_TOKEN = re.compile(r'"[^"]*"|\{[^}]*\}|[()]|[^\s()"{}]+')
FTS_BARE = re.compile(r"^\w+\*?$|^(AND|OR|NOT)$|^\w+:$|^:$|^\w+:\w+\*?$")


def fts_fix(query):
    """Quote bare tokens FTS5 cannot parse (e.g. hyphenated `vision-language`) while
    keeping operators, parentheses, phrases and column filters intact."""
    out = []
    for tok in FTS_TOKEN.findall(query):
        if tok.startswith(('"', "{")) or tok in "()" or FTS_BARE.match(tok):
            out.append(tok)
        else:
            out.append('"' + tok.rstrip("*").replace('"', '""') + '"' + ("*" if tok.endswith("*") else ""))
    return " ".join(out)


_warned = set()


def fts_match(db, query, sql, params=()):
    """Run an FTS5 query, quoting hyphenated words first. If it is still not valid
    FTS5, search it as plain words and SAY so: that changes its meaning."""
    try:
        return db.execute(sql, (fts_fix(query),) + tuple(params)).fetchall()
    except sqlite3.OperationalError as e:
        plain = " ".join('"' + w.replace('"', '""') + '"' for w in re.findall(r"[\w-]+", query))
        if query not in _warned:
            _warned.add(query)
            print(f"# WARNING: not valid FTS5 ({e}); searched as plain words, all required: {plain}")
        return db.execute(sql, (plain,) + tuple(params)).fetchall()


def paper_filters(args, alias="p"):
    """WHERE fragments for the common --venue/--year/--type/--task/--new filters."""
    where, params = [], []
    if getattr(args, "venue", None):
        where.append(f"{alias}.conference IN ({','.join('?' * len(args.venue))})")
        params += [v.upper() for v in args.venue]
    if getattr(args, "year", None):
        where.append(f"{alias}.year IN ({','.join('?' * len(args.year))})")
        params += [str(y) for y in args.year]
    if getattr(args, "type", None):
        where.append(f"{alias}.paper_type = ?")
        params.append(args.type)
    if getattr(args, "task", None):
        where.append(f"{alias}.primary_task LIKE ?")
        params.append(f"%{args.task}%")
    if getattr(args, "new", False):
        where.append(f"{alias}.task_novelty = 'new'")
    return where, params


def cmd_search(args):
    """Keyword search; several queries are fused by reciprocal rank."""
    db = connect(args.db)
    where, params = paper_filters(args)
    sql = ("SELECT p.paper_id FROM fts JOIN papers p ON p.id = fts.rowid WHERE fts MATCH ?"
           + "".join(f" AND {w}" for w in where) + f" ORDER BY {BM25} LIMIT ?")
    score = {}
    for q in args.query:
        hits = [r[0] for r in fts_match(db, q, sql, params + [args.pool])]
        total = fts_match(db, q, "SELECT count(*) FROM fts JOIN papers p ON p.id = fts.rowid WHERE fts MATCH ?"
                          + "".join(f" AND {w}" for w in where), params)[0][0]
        print(f"# {total:6d} matches  {q}")
        for rank, pid in enumerate(hits):
            score[pid] = score.get(pid, 0.0) + 1.0 / (60 + rank)
    best = sorted(score, key=score.get, reverse=True)[:args.k]
    print(f"# showing {len(best)} of {len(score)} distinct papers"
          f" (pooled from at most the top {args.pool} of each query)\n")
    for pid in best:
        row = db.execute("SELECT paper_id, conference, year, title, key_contribution FROM papers"
                         " WHERE paper_id = ?", (pid,)).fetchone()
        print(card(row, args.long))


SECTION_NAMES = {"problem": "Problem", "io": "Input / Output", "method": "Method", "results": "Results",
                 "baselines": "Baselines & Comparisons", "prior": "Relation to Prior Work",
                 "why": "Why It Matters / Open Questions"}


def cmd_show(args):
    """Print notes, optionally only some body sections; image links are dropped."""
    db = connect(args.db)
    for pid in args.paper_id:
        row = db.execute("SELECT note_path, pdf_url, title FROM papers WHERE paper_id = ?", (pid,)).fetchone()
        if not row:
            print(f"### {pid}: not in the database\n")
            continue
        text = open(os.path.join(VAULT, row[0]), encoding="utf-8").read()
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)\n?", "", text)
        head, body = text[4:].split("\n---\n", 1)
        print(f"### {pid}  {row[2]}  ({row[0]})")
        if not args.sections or args.frontmatter:
            print(head.strip())
        if args.sections:
            wanted = {SECTION_NAMES.get(s, s) for s in args.sections}
            for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, re.S | re.M):
                if m.group(1).strip() in wanted:
                    sec = m.group(2).strip()
                    if args.max_chars and len(sec) > args.max_chars:
                        sec = sec[:args.max_chars].rstrip() + " [...]"
                    print(f"\n## {m.group(1).strip()}\n{sec}")
        else:
            print(body.strip())
        print()


def cmd_like(args):
    """Papers that cite the same works (bibliographic coupling), rarer shared works weighing more.
    The works are those a vault paper cites, or a given list (e.g. a draft's own references)."""
    db = connect(args.db)
    if args.works:
        mine, unknown = [], []
        for w in args.works:
            found = resolve_work(db, w)
            if len(found) == 1:
                mine += found[0][1]
                print(f"#   cited by {found[0][2]:5d} papers: {w}")
            else:
                unknown.append(w)
        print(f"# {len(args.works) - len(unknown)} of {len(args.works)} given works are cited in the vault")
        for w in unknown:
            print(f"#   not matched (absent or ambiguous; check with `citers`): {w}")
        mine = sorted(set(mine))
        exclude = ""
    elif args.paper_id:
        row = db.execute("SELECT title FROM papers WHERE paper_id = ?", (args.paper_id,)).fetchone()
        if not row:
            sys.exit(f"{args.paper_id}: not in the database")
        mine = [r[0] for r in db.execute("SELECT DISTINCT ntitle FROM relations WHERE paper_id = ?",
                                         (args.paper_id,))]
        print(f"# {args.paper_id}: {row[0]}\n# cites {len(mine)} distinct works in builds_on/compares_to")
        exclude = args.paper_id
    else:
        sys.exit("give a paper ID or --works")
    n = db.execute("SELECT count(*) FROM papers").fetchone()[0]
    df = {}
    for w in mine:
        df[w] = db.execute("SELECT count(DISTINCT paper_id) FROM relations WHERE ntitle = ?", (w,)).fetchone()[0]
    # Works nearly everyone cites (popular backbones, standard baselines) say little
    # about being in the same subfield; drop them instead of letting them add up.
    common = [w for w in mine if df[w] > args.max_share / 100 * n]
    mine = [w for w in mine if w not in common]
    if common:
        print(f"# ignoring {len(common)} work(s) cited by more than {args.max_share:g}% of papers "
              f"(--max-share): " + "; ".join(common[:5]) + (" ..." if len(common) > 5 else ""))
    if len(mine) < 3:
        print("# few usable citations: shared-citation similarity is unreliable here, "
              "search on the key terms instead")
    if not mine:
        return
    where, params = paper_filters(args)
    rows = db.execute(f"""
        WITH mine(ntitle) AS (VALUES {','.join(['(?)'] * len(mine))}),
             df AS (SELECT r.ntitle, count(DISTINCT r.paper_id) n FROM relations r JOIN mine USING (ntitle)
                    GROUP BY r.ntitle)
        SELECT p.paper_id, p.conference, p.year, p.title, p.key_contribution,
               sum(ln(? * 1.0 / df.n)) AS s, count(DISTINCT r.ntitle) AS shared
        FROM (SELECT DISTINCT paper_id, ntitle FROM relations) r JOIN df USING (ntitle)
        JOIN papers p ON p.paper_id = r.paper_id
        WHERE r.paper_id != ? {''.join(f' AND {w}' for w in where)}
        GROUP BY r.paper_id ORDER BY s DESC LIMIT ?""",
        mine + [n, exclude] + params + [args.k]).fetchall()
    print("# ranked by score = sum over shared works of ln(papers / papers citing that work)\n")
    for r in rows:
        shared = sorted({x[0] for x in db.execute(
            f"SELECT ntitle FROM relations WHERE paper_id = ? AND ntitle IN ({','.join('?' * len(mine))})",
            [r[0]] + mine)}, key=lambda w: df[w])
        print(f"[score {r[5]:.1f}, shares {r[6]}] " + card(r[:5], args.long))
        print("    shared (rarest first): " + "; ".join(shared[:3]) + (" ..." if len(shared) > 3 else ""))


def _citing(db, ntitles):
    return db.execute(f"SELECT count(DISTINCT paper_id) FROM relations WHERE ntitle IN "
                      f"({','.join('?' * len(ntitles))})", ntitles).fetchone()[0]


def resolve_work(db, ref):
    """A work reference -> [(label, [cited titles], papers citing it)].
    A vault paper ID covers every cited title linked to that paper (exact or fuzzy), and so
    does an exact cited title that is linked to one. A partial title lists the matching cited
    titles (whole words), most cited first."""
    if PAPER_ID.match(ref):
        row = db.execute("SELECT title, ntitle FROM papers WHERE paper_id = ?", (ref,)).fetchone()
        if not row:
            return []
        nts = sorted({r[0] for r in db.execute("SELECT DISTINCT ntitle FROM relations WHERE vault_paper_id = ?",
                                               (ref,))} | {row[1]})
        return [(f"{ref}: {row[0]}", nts, _citing(db, nts))]
    nt = norm_title(ref)
    linked = db.execute("SELECT vault_paper_id FROM relations WHERE ntitle = ? AND vault_paper_id IS NOT NULL"
                        " LIMIT 1", (nt,)).fetchone() or \
        db.execute("SELECT paper_id FROM papers WHERE ntitle = ? LIMIT 1", (nt,)).fetchone()
    if linked:
        return resolve_work(db, linked[0])
    n = _citing(db, [nt])
    if n:
        return [(nt, [nt], n)]
    return [(r[0], [r[0]], r[1]) for r in db.execute(
        "SELECT ntitle, count(DISTINCT paper_id) n FROM relations WHERE (' ' || ntitle || ' ') LIKE ?"
        " GROUP BY ntitle ORDER BY n DESC LIMIT 10", (f"% {nt} %",))]


def cmd_citers(args):
    """Papers whose builds_on / compares_to names a given work."""
    db = connect(args.db)
    works = resolve_work(db, args.work)
    if not works:
        sys.exit(f"no cited work matches {args.work!r}")
    if len(works) > 1:
        print(f"# {args.work!r} matches several cited titles (papers citing each, most first);"
              " the same work can appear under more than one title, run `citers` on each variant:")
        for w, _, n in works:
            print(f"#   {n:5d}  {w}")
        return
    label, nts, _ = works[0]
    kinds = [args.kind] if args.kind else ["builds_on", "compares_to"]
    where, params = paper_filters(args)
    rows = db.execute(f"""
        SELECT p.paper_id, p.conference, p.year, p.title, p.key_contribution,
               group_concat(DISTINCT r.kind) FROM relations r JOIN papers p ON p.paper_id = r.paper_id
        WHERE r.ntitle IN ({','.join('?' * len(nts))}) AND r.kind IN ({','.join('?' * len(kinds))})
              {''.join(f' AND {w}' for w in where)}
        GROUP BY p.paper_id ORDER BY p.year DESC, p.paper_id LIMIT ?""",
        nts + kinds + params + [args.k]).fetchall()
    total = db.execute(f"SELECT count(DISTINCT paper_id) FROM relations WHERE ntitle IN "
                       f"({','.join('?' * len(nts))}) AND kind IN ({','.join('?' * len(kinds))})",
                       nts + kinds).fetchone()[0]
    variants = f" (cited under {len(nts)} titles)" if len(nts) > 1 else ""
    print(f"# {total} papers cite '{label}'{variants} ({' / '.join(kinds)}); showing {len(rows)}\n")
    for r in rows:
        print(f"[{r[5]}] " + card(r[:5], args.long))


def topic_ids(db, args):
    """The paper set a trend is about, and a label for it."""
    if args.query:
        ids = {r[0] for r in fts_match(db, args.query, "SELECT p.paper_id FROM fts JOIN papers p "
                                       "ON p.id = fts.rowid WHERE fts MATCH ?")}
        return ids, f"match {args.query!r}"
    if args.cites:
        works = resolve_work(db, args.cites)
        if len(works) != 1:
            sys.exit(f"--cites {args.cites!r} matches {len(works)} cited titles; "
                     f"use `citers` to pick one: {[w for w, _, _ in works[:5]]}")
        label, nts, _ = works[0]
        kinds = [args.kind] if args.kind else ["builds_on", "compares_to"]
        ids = {r[0] for r in db.execute(f"SELECT paper_id FROM relations WHERE ntitle IN "
                                        f"({','.join('?' * len(nts))}) AND kind IN "
                                        f"({','.join('?' * len(kinds))})", nts + kinds)}
        return ids, f"cite '{label}' ({' / '.join(kinds)})"
    field, _, value = args.tag.partition("=")
    ids = {r[0] for r in db.execute("SELECT paper_id FROM tags WHERE field = ? AND value = ? COLLATE NOCASE",
                                    (field, value))}
    return ids, f"have {field} = {value} (case-insensitive, exact value)"


def cmd_trend(args):
    """Share of papers per conference edition, in submission-deadline order."""
    db = connect(args.db)
    ids, label = topic_ids(db, args)
    edition_of = dict(db.execute("SELECT paper_id, edition FROM papers"))
    editions = db.execute("SELECT edition, conference, year, n_papers FROM editions").fetchall()
    if args.venue:
        editions = [e for e in editions if e[1] in {v.upper() for v in args.venue}]
    uncommitted = {e for e, fp in db.execute("SELECT edition, fingerprint FROM editions")
                   if fp.startswith("mtime:")}
    base = None
    if args.within:
        base = {r[0] for r in fts_match(db, args.within, "SELECT p.paper_id FROM fts JOIN papers p "
                                        "ON p.id = fts.rowid WHERE fts MATCH ?")}
        ids &= base
    count = lambda s: {e: sum(1 for p in s if edition_of.get(p) == e) for e, *_ in editions}
    hits = count(ids)
    denom = count(base) if base is not None else {e: n for e, _, _, n in editions}
    print(f"# share of {'the papers matching ' + repr(args.within) if base is not None else 'all papers'}"
          f" that {label}: {len(ids)} papers")
    print("# editions in submission-deadline order. Prefer same-venue comparisons (column `prev`, the same"
          " venue's previous edition); compare vision and ML venues separately")
    print(f"{'edition':12s} {'family':6s} {'deadline':8s} {'base':>7s} {'hits':>6s} {'share':>7s} {'prev':>7s}")
    prev_share, prev_n = {}, {}
    for e, conf, year, n in sorted(editions, key=lambda t: (deadline(t[1], t[2]), t[0])):
        d = denom[e]
        share = 100 * hits[e] / d if d else 0.0
        prev = f"{prev_share[conf]:6.2f}%" if conf in prev_share else "      -"
        # Editions only grow, so one under half its predecessor is still being summarized;
        # uncommitted notes mean the pipeline has not published it yet either.
        flag = ("  INCOMPLETE? under half the previous edition, ignore this row" if n < 0.5 * prev_n.get(conf, 0)
                else "  (uncommitted notes: may still be in progress)" if e in uncommitted else "")
        prev_n[conf] = n
        print(f"{e:12s} {'vision' if conf in VISION else 'ml':6s} {deadline(conf, year):8s} "
              f"{d:7d} {hits[e]:6d} {share:6.2f}% {prev}{flag}")
        if not flag:
            prev_share[conf] = share
    if args.sample:
        import random
        pick = random.Random(args.seed).sample(sorted(ids), min(args.sample, len(ids)))
        print(f"\n# random sample of {len(pick)} matching papers (seed {args.seed}; check how many are on topic):")
        for pid in pick:
            row = db.execute("SELECT paper_id, conference, year, title, key_contribution FROM papers"
                             " WHERE paper_id = ?", (pid,)).fetchone()
            print(card(row))


def cmd_sql(args):
    """Read-only SQL; tab-separated output with a header line."""
    db = connect(args.db)
    query = args.query
    if args.ids_file:
        ids = [l.split()[0] for l in open(args.ids_file) if l.strip() and not l.startswith("#")]
        query = query.replace(":ids", ",".join("'" + i.replace("'", "''") + "'" for i in ids))
    try:
        cur = db.execute(query)
    except sqlite3.Error as e:
        sys.exit(f"SQL error: {e}")
    if cur.description:
        print("\t".join(d[0] for d in cur.description))
        for i, row in enumerate(cur):
            if i >= args.limit:
                print(f"# ... truncated at {args.limit} rows (use --limit)")
                break
            print("\t".join("" if v is None else str(v) for v in row))


# ---------------------------------------------------------------------------
# BibTeX from DBLP. dblp.org's website and search API sit behind an anti-bot
# challenge for scripted clients, so this uses DBLP's official SPARQL endpoint
# (same data) and assembles the entry from its fields. Every lookup is cached
# in dblp_cache.db next to the database, so each work is fetched only once.
# ---------------------------------------------------------------------------

SPARQL = "https://sparql.dblp.org/sparql"
DBLP_PREFIX = "PREFIX dblp: <https://dblp.org/rdf/schema#>\n"
_last_request = [0.0]


class DblpUnavailable(Exception):
    pass


def sparql(query, retries=4):
    """Run one SPARQL query politely: >= 1.5 s between requests, back off on 429/5xx."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request
    for attempt in range(retries):
        wait = _last_request[0] + 1.5 - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()
        req = urllib.request.Request(
            SPARQL, data=urllib.parse.urlencode({"query": DBLP_PREFIX + query}).encode(),
            headers={"Accept": "application/sparql-results+json", "User-Agent": "PapersVault-vault.py"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.load(r)
            return [{k: v["value"] for k, v in b.items()} for b in data["results"]["bindings"]]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise DblpUnavailable(f"HTTP {e.code} from DBLP")
            if attempt == retries - 1:
                raise DblpUnavailable(f"DBLP still answering HTTP {e.code} after {retries} tries")
            delay = int(e.headers.get("Retry-After") or 0) or 10 * 2 ** attempt
            print(f"  DBLP busy (HTTP {e.code}), waiting {delay}s", file=sys.stderr)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == retries - 1:
                raise DblpUnavailable(f"cannot reach DBLP: {e}")
            time.sleep(10 * 2 ** attempt)


def sparql_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def surname(name):
    name = re.sub(r"\s+\d{4}$", "", str(name or "")).strip()  # DBLP homonym suffix "Miao Zhang 0022"
    return norm_title(name.split()[-1]) if name else ""


def dblp_candidates(title, years):
    """DBLP records whose title matches: exact first, then a case/punctuation-insensitive
    match restricted to the given years (unrestricted if none). Returns dicts with pub,
    title, year, venue, first author."""
    base = re.sub(r"[.\s]+$", "", title.strip())
    common = ("?pub dblp:title ?title ; dblp:yearOfPublication ?year . "
              "OPTIONAL { ?pub dblp:publishedIn ?venue } "
              "OPTIONAL { ?pub dblp:hasSignature ?s . ?s dblp:signatureOrdinal 1 ; dblp:signatureDblpName ?first }")
    rows = sparql(f"SELECT DISTINCT ?pub ?title ?year ?venue ?first WHERE {{ "
                  f"VALUES ?title {{ {sparql_str(base + '.')} {sparql_str(base)} }} {common} }}")
    if rows:
        return rows
    words = norm_title(base).split()
    if not words:
        return []
    pattern = "[^a-z0-9]+".join(re.escape(w) for w in words)
    year_clause = ""
    if years:
        vals = " ".join(f'"{y}"^^<http://www.w3.org/2001/XMLSchema#gYear>' for y in sorted(years))
        year_clause = f"VALUES ?year {{ {vals} }} "
    return sparql(f"SELECT DISTINCT ?pub ?title ?year ?venue ?first WHERE {{ {year_clause}{common} "
                  f"FILTER(REGEX(LCASE(?title), {sparql_str(pattern)})) }} LIMIT 50")


def pick_candidate(rows, title, author, year):
    """Best DBLP record for a title -> (row, note) or (None, None).
    Requires a (near-)identical title. The first author's surname must match too, except for
    an exact title within a year, which is accepted with a note: the vault note's author list
    may be the wrong one. Prefers the published version over arXiv (CoRR), then the closest year."""
    import difflib
    want = norm_title(title)
    best = None
    for r in rows:
        sim = difflib.SequenceMatcher(None, want, norm_title(r["title"])).ratio()
        if sim < 0.93:
            continue
        note = None
        if author and r.get("first") and surname(r["first"]) != surname(author):
            if sim < 0.99 or (year and abs(int(r["year"]) - int(year)) > 1):
                continue
            note = (f"first author differs: our record says {author!r}, DBLP says "
                    f"{re.sub(r' [0-9]{4}$', '', r['first'])!r}")
        informal = r.get("venue") == "CoRR"
        key = (informal, note is not None, -sim, abs(int(r["year"]) - int(year)) if year else 0)
        if best is None or key < best[0]:
            best = (key, r, note)
    return (best[1], best[2]) if best else (None, None)


# How each vault conference appears in DBLP's publishedIn ("ECCV (12)" for ECCV volumes),
# and its full name for entries built from a note.
DBLP_VENUE = {"CVPR": "CVPR", "ICCV": "ICCV", "ECCV": "ECCV", "NEURIPS": "NeurIPS", "ICLR": "ICLR",
              "ICML": "ICML", "WACV": "WACV"}
VENUE_NAMES = {"CVPR": "IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)",
               "ICCV": "IEEE/CVF International Conference on Computer Vision (ICCV)",
               "ECCV": "European Conference on Computer Vision (ECCV)",
               "NEURIPS": "Advances in Neural Information Processing Systems (NeurIPS)",
               "ICLR": "International Conference on Learning Representations (ICLR)",
               "ICML": "International Conference on Machine Learning (ICML)",
               "WACV": "IEEE/CVF Winter Conference on Applications of Computer Vision (WACV)"}


def dblp_by_venue(title, author, conf, year):
    """The proceedings record of a vault paper whose proceedings title differs from the one
    we know (common: arXiv title vs camera-ready title): same venue, year and first author,
    and most of the title's words in common."""
    venue = DBLP_VENUE.get(conf)
    if not venue or not author:
        return None
    # ECCV is split into numbered volumes ("ECCV (12)"); the others are a single string.
    venue_match = (f"FILTER(STRSTARTS(?venue, {sparql_str(venue)}))" if conf == "ECCV"
                   else f"VALUES ?venue {{ {sparql_str(venue)} }}")
    rows = sparql(f"""SELECT DISTINCT ?pub ?title ?year ?venue ?first WHERE {{
        VALUES ?year {{ "{year}"^^<http://www.w3.org/2001/XMLSchema#gYear> }} {venue_match}
        ?pub dblp:yearOfPublication ?year ; dblp:publishedIn ?venue ; dblp:title ?title ;
             dblp:hasSignature ?s . ?s dblp:signatureOrdinal 1 ; dblp:signatureDblpName ?first .
        FILTER(CONTAINS(LCASE(?first), {sparql_str(surname(author))}))
    }} LIMIT 200""")
    want = set(norm_title(title).split())
    best = None
    for r in rows:
        if surname(r["first"]) != surname(author):
            continue
        got = set(norm_title(r["title"]).split())
        jac = len(want & got) / max(1, len(want | got))
        if jac >= 0.5 and (best is None or jac > best[0]):
            best = (jac, r)
    return best[1] if best else None


def dblp_bibtex(pub):
    """Assemble a BibTeX entry for one DBLP record."""
    rows = sparql(f"""SELECT ?title ?type ?year ?pages ?doi ?ee ?venue ?book ?publisher ?journal
        ?volume ?number ?ord ?name WHERE {{
        BIND(<{pub}> AS ?pub)
        ?pub dblp:title ?title ; dblp:bibtexType ?type ; dblp:yearOfPublication ?year .
        OPTIONAL {{ ?pub dblp:pagination ?pages }}
        OPTIONAL {{ ?pub dblp:doi ?doi }}
        OPTIONAL {{ ?pub dblp:primaryDocumentPage ?ee }}
        OPTIONAL {{ ?pub dblp:publishedIn ?venue }}
        OPTIONAL {{ ?pub dblp:publishedAsPartOf ?proc . ?proc dblp:title ?book .
                    OPTIONAL {{ ?proc dblp:publishedBy ?publisher }} }}
        OPTIONAL {{ ?pub dblp:publishedInJournal ?journal }}
        OPTIONAL {{ ?pub dblp:publishedInJournalVolume ?volume }}
        OPTIONAL {{ ?pub dblp:publishedInJournalVolumeIssue ?number }}
        OPTIONAL {{ ?pub dblp:hasSignature ?sig . ?sig dblp:signatureOrdinal ?ord ; dblp:signatureDblpName ?name }}
    }}""")
    if not rows:
        return None
    r0 = rows[0]
    authors, seen = [], set()
    for r in sorted(rows, key=lambda r: int(r.get("ord", 0))):
        if r.get("name") and r["ord"] not in seen:
            seen.add(r["ord"])
            authors.append(re.sub(r"\s+\d{4}$", "", r["name"]))
    kind = r0["type"].rsplit("#", 1)[-1].lower()
    key = "DBLP:" + pub.split("/rec/", 1)[1]
    f = {"author": " and ".join(authors), "title": re.sub(r"\.$", "", r0["title"])}
    if kind == "inproceedings":
        f["booktitle"] = r0.get("book") or r0.get("venue", "")
        f["publisher"] = r0.get("publisher")
    elif kind == "article":
        f["journal"] = r0.get("journal") or r0.get("venue", "")
        f["volume"], f["number"] = r0.get("volume"), r0.get("number")
        m = re.match(r"abs/(\d{4}\.\d{4,5})", r0.get("volume") or "")
        if f["journal"] == "CoRR" and m:
            f["eprinttype"], f["eprint"] = "arXiv", m.group(1)
    else:
        kind = "misc"
        f["howpublished"] = r0.get("book") or r0.get("venue")
    f["pages"] = (r0.get("pages") or "").replace("-", "--") or None
    f["year"] = r0["year"]
    f["doi"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", r0["doi"]) if r0.get("doi") else None
    f["url"] = r0.get("ee")
    body = ",\n".join(f"  {k:<10}= {{{v}}}" for k, v in f.items() if v)
    return f"@{kind}{{{key},\n{body}\n}}"


def cache_db(db_path):
    c = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(db_path)), "dblp_cache.db"))
    c.execute("CREATE TABLE IF NOT EXISTS lookups(lookup TEXT PRIMARY KEY, pub TEXT, venue TEXT,"
              " year TEXT, note TEXT, bibtex TEXT, fetched_at TEXT)")
    return c


def fallback_entry(ref, title, author, year, venue, url, in_vault):
    words = [w for w in norm_title(title).split() if len(w) > 3]
    first = words[0] if words else "untitled"
    if in_vault:
        key = f"vault:{ref}"
        head = "% vault.py: no DBLP match -- entry built from the vault note, check it"
        kind, extra = "inproceedings", f"  booktitle = {{{VENUE_NAMES.get(venue, venue)}}},\n"
    else:
        key = f"unresolved:{surname(author) or 'anon'}{year or ''}{first}"
        head = "% vault.py: NOT FOUND in DBLP -- placeholder from the citing note, check it by hand"
        kind, extra = "misc", (f"  note      = {{{venue}}},\n" if venue else "")
    lines = [f"  author    = {{{author}}}," if author else "", f"  title     = {{{title}}},", extra.rstrip("\n"),
             f"  year      = {{{year}}}," if year else "", f"  url       = {{{url}}}," if url else ""]
    return head + f"\n@{kind}{{{key},\n" + "\n".join(l for l in lines if l) + "\n}"


def lookup_dblp(title, author, year, conf=None):
    """-> (pub, venue, year, note) for the best DBLP record, or Nones."""
    years = {int(year) + d for d in (-1, 0, 1)} if year else set()
    cand, note = pick_candidate(dblp_candidates(title, years), title, author, year)
    if conf and DBLP_VENUE.get(conf) and (cand is None or cand.get("venue") == "CoRR"):
        # A vault paper is a proceedings paper: if we only found the arXiv version (or
        # nothing), its proceedings title probably differs from ours -- look by venue.
        proc = dblp_by_venue(title, author, conf, year)
        if proc:
            cand, note = proc, f"proceedings title differs: {re.sub(r'[.]$', '', proc['title'])!r}"
    if cand is None:
        return None, None, None, None
    return cand["pub"], cand.get("venue"), cand.get("year"), note


def cmd_bib(args):
    """BibTeX for vault papers (by ID) or cited works (by title), always looked up in DBLP."""
    db = connect(args.db)
    cache = cache_db(args.db)
    refs = list(args.ref)
    if args.file:
        refs += [l.strip() for l in open(args.file) if l.strip() and not l.startswith("#")]
    refs = list(dict.fromkeys(refs))  # drop duplicates, keep order
    out, check, keys = [], [], {}
    offline = None  # set once DBLP is unreachable: the remaining refs fall back
    for ref in refs:
        url, in_vault, conf = None, bool(PAPER_ID.match(ref)), None
        if in_vault:
            row = db.execute("SELECT title, authors, first_author, year, conference, pdf_url FROM papers"
                             " WHERE paper_id = ?", (ref,)).fetchone()
            if not row:
                print(f"{ref}: not in the database, skipped", file=sys.stderr)
                continue
            title, authors, author, year, conf, url = row
            venue = conf
            author_field = " and ".join(a.strip() for a in authors.split(";") if a.strip()) or author
        else:
            title, author_field = ref, None
            row = db.execute("SELECT first_author, venue, count(*) n FROM relations WHERE ntitle = ?"
                             " GROUP BY first_author, venue ORDER BY n DESC LIMIT 1", (norm_title(ref),)).fetchone()
            author, venue = (row[0], row[1]) if row else ("", "")
            m = re.search(r"(19|20)\d{2}", venue or "")
            year = m.group(0) if m else None
        lookup = f"{norm_title(title)}|{surname(author)}|{conf or ''}"
        hit = None if args.refresh else cache.execute(
            "SELECT pub, venue, year, note, bibtex FROM lookups WHERE lookup = ?", (lookup,)).fetchone()
        if hit is None and not offline:
            print(f"looking up: {title[:80]}", file=sys.stderr)
            try:
                pub, dvenue, dyear, note = lookup_dblp(title, author, year, conf)
                hit = (pub, dvenue, dyear, note, dblp_bibtex(pub) if pub else None)
                cache.execute("INSERT OR REPLACE INTO lookups VALUES (?,?,?,?,?,?,?)",
                              (lookup,) + hit + (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
                cache.commit()
            except DblpUnavailable as e:
                offline = str(e)
                print(f"  {offline}: the remaining references get placeholder entries;"
                      " re-run later (finished lookups are cached)", file=sys.stderr)
        pub, dvenue, dyear, note, bib = hit or (None, None, None, None, None)
        label = f"% vault.py ref: {ref}\n"
        if not bib:
            why = (f"DBLP unavailable ({offline}), re-run later" if hit is None
                   else "not found in DBLP")
            check.append(f"{ref}: {why}; entry built from {'the note' if in_vault else 'the citation'}")
            out.append(label + fallback_entry(ref, title, author_field if in_vault else author, year,
                                              venue, url, in_vault))
            continue
        key = bib.split("{", 1)[1].split(",", 1)[0]
        if key in keys:
            print(f"{ref}: same DBLP record as {keys[key]} ({key}), entry not repeated", file=sys.stderr)
            continue
        keys[key] = ref
        reasons = [note] if note else []
        if in_vault and dvenue == "CoRR":
            reasons.append(f"only the arXiv version found, but the vault has it as {conf} {year}")
        elif in_vault and dvenue and DBLP_VENUE.get(conf) and not dvenue.startswith(DBLP_VENUE[conf]):
            reasons.append(f"DBLP venue {dvenue!r} differs from the vault's {conf}")
        if in_vault and dyear and str(dyear) != str(year):
            reasons.append(f"DBLP year {dyear} differs from the vault's {year}")
        for r in reasons:
            check.append(f"{ref}: {r}")
        flag = "".join(f"% vault.py: CHECK -- {r}\n" for r in reasons)
        out.append(label + flag + bib)
    print("\n\n".join(out))
    print(f"{len(out)} entries; {len(check)} to check by hand", file=sys.stderr)
    for c in check:
        print(f"  CHECK {c}", file=sys.stderr)
    if offline:
        sys.exit(2)


def cmd_cite(args):
    """Replace [paper_id] / [cited title] markers in a draft with \\cite{key}, using the
    `% vault.py ref:` labels that `bib` writes before each entry."""
    bib = open(args.bib, encoding="utf-8").read()
    keymap = {ref.strip(): key.strip() for ref, key in
              re.findall(r"^% vault\.py ref: (.+)\n(?:%.*\n)*@\w+\{([^,]+),", bib, re.M)}
    text = open(args.tex, encoding="utf-8").read()
    missing = set()

    def sub(m):
        parts = [x.strip() for x in re.split(r"[;,]\s*(?=[A-Z]+\d{8}\b)", m.group(1))]
        if all(x in keymap for x in parts):
            return "\\cite{" + ",".join(keymap[x] for x in parts) + "}"
        if any(PAPER_ID.match(x) for x in parts):
            missing.update(x for x in parts if x not in keymap)
        return m.group(0)

    text = re.sub(r"\[([^\[\]\n]+)\]", sub, text)
    while True:  # merge \cite{a} \cite{b} into \cite{a,b}
        merged = re.sub(r"\\cite\{([^}]*)\}\s*\\cite\{([^}]*)\}", r"\\cite{\1,\2}", text)
        if merged == text:
            break
        text = merged
    sys.stdout.write(text)
    for m in sorted(missing):
        print(f"marker not in {args.bib}, left as is: {m}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="create or incrementally update the database")
    b.add_argument("--db", default=DEFAULT_DB, help="database path (default: vault.db next to this script)")
    b.add_argument("--full", action="store_true", help="rebuild from scratch")
    b.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1),
                   help="parallel note parsers (default: min(8, CPUs))")
    b.set_defaults(func=cmd_build)
    s = sub.add_parser("status", help="check whether the database is current (exit 0) or stale (exit 1)")
    s.add_argument("--db", default=DEFAULT_DB, help="database path (default: vault.db next to this script)")
    s.set_defaults(func=cmd_status)

    def common(sp, filters=True, k=20):
        sp.add_argument("--db", default=DEFAULT_DB, help="database path")
        if filters:
            sp.add_argument("--venue", nargs="+", help="conference(s), e.g. CVPR ICLR")
            sp.add_argument("--year", nargs="+", help="year(s)")
            sp.add_argument("--type", help="paper_type: regular | benchmark | dataset | position | survey")
            sp.add_argument("--task", help="primary_task contains this text")
            sp.add_argument("--new", action="store_true", help="only papers that define a new task")
        if k:
            sp.add_argument("-k", type=int, default=k, help=f"results to show (default {k})")
            sp.add_argument("--long", action="store_true", help="full key contribution instead of a truncated one")

    s = sub.add_parser("search", help="keyword search (FTS5 syntax: \"phrase\", OR, AND, NOT, prefix*)")
    s.add_argument("query", nargs="+", help="one or more queries; results are fused")
    s.add_argument("--pool", type=int, default=200, help="hits taken from each query before fusing")
    common(s)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("show", help="print notes (without image links)")
    s.add_argument("paper_id", nargs="+")
    s.add_argument("--sections", nargs="+", metavar="S",
                   help=f"only these body sections: {' '.join(SECTION_NAMES)}")
    s.add_argument("--frontmatter", action="store_true", help="with --sections, also print the frontmatter")
    s.add_argument("--max-chars", type=int, default=0,
                   help="with --sections, cut each section to this many characters (e.g. 600 for screening)")
    common(s, filters=False, k=0)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("like", help="papers citing the same works as a given paper, or as a list of works")
    s.add_argument("paper_id", nargs="?")
    s.add_argument("--works", nargs="+", metavar="TITLE",
                   help="instead of a paper: cited works (titles or paper IDs), e.g. a draft's references")
    s.add_argument("--max-share", type=float, default=1.0,
                   help="ignore works cited by more than this %% of all papers (default 1)")
    common(s)
    s.set_defaults(func=cmd_like)

    s = sub.add_parser("citers", help="papers that build on / compare to a work (paper ID or cited title)")
    s.add_argument("work")
    s.add_argument("--kind", choices=["builds_on", "compares_to"])
    common(s, k=50)
    s.set_defaults(func=cmd_citers)

    s = sub.add_parser("trend", help="share of papers per conference edition, in deadline order")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="FTS5 text query")
    g.add_argument("--cites", help="papers citing this work (paper ID or cited title)")
    g.add_argument("--tag", help="FIELD=VALUE, e.g. method_family=flow-matching")
    s.add_argument("--kind", choices=["builds_on", "compares_to"], help="with --cites")
    s.add_argument("--within", metavar="QUERY",
                   help="share within the papers matching this FTS5 query instead of within all papers")
    s.add_argument("--venue", nargs="+", help="only these conferences, e.g. CVPR ECCV ICCV")
    s.add_argument("--sample", type=int, default=0, help="also print N random matching papers")
    s.add_argument("--seed", type=int, default=0, help="seed for --sample (default 0)")
    common(s, filters=False, k=0)
    s.set_defaults(func=cmd_trend)

    s = sub.add_parser("sql", help="read-only SQL against vault.db")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--ids-file", help="file with one paper ID per line; replaces :ids in the query, "
                   "e.g. ... WHERE paper_id IN (:ids)")
    common(s, filters=False, k=0)
    s.set_defaults(func=cmd_sql)

    s = sub.add_parser("bib", help="BibTeX from DBLP for vault paper IDs or cited titles (needs internet)")
    s.add_argument("ref", nargs="*", help="paper IDs (CVPR20250100) and/or cited titles")
    s.add_argument("--file", help="file with one paper ID or title per line")
    s.add_argument("--refresh", action="store_true", help="ignore cached lookups")
    common(s, filters=False, k=0)
    s.set_defaults(func=cmd_bib)

    s = sub.add_parser("cite", help="replace [ID] / [title] markers in a draft with \\cite{key} from a bib file")
    s.add_argument("tex", help="draft with markers such as [CVPR20250100] or [CVPR20250100, ICLR20240047]")
    s.add_argument("--bib", required=True, help="the .bib written by `vault.py bib`")
    s.set_defaults(func=cmd_cite)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
