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
    known = dict(db.execute("SELECT edition, fingerprint FROM editions"))
    present = edition_dirs()
    fps = fingerprints(present)
    changed = False
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
        # Link citations to vault papers by normalised title; redone in full
        # because a new edition can resolve citations made by older ones.
        db.execute("UPDATE relations SET vault_paper_id = ("
                   " SELECT p.paper_id FROM papers p WHERE p.ntitle = relations.ntitle LIMIT 1)")
        db.execute("INSERT INTO fts(fts) VALUES ('optimize')")
    db.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                   [("git_head", git_head() or ""),
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
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
