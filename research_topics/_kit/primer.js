/* PapersVault primer kit -- behaviour shared by the hand-built research_topics/<slug>/index.html pages.
   Pages load it near the end of <body> as ../_kit/primer.js, before their own widget scripts (window.Primer is
   ready at once; the page itself is processed at DOMContentLoaded). `vault.py cards <slug>` inlines it into .bundle.html.

   What it does with the markup a page writes by hand:
     <a class="paper" data-paper="CVPR20250100">DKDM</a>   chip + click card (data from <script id="papers">,
                                                            filled by `vault.py cards <slug>`)
     <ul class="reading"><li data-paper="ID">...</li>       persistent checkbox per item + progress in the heading
     <figure class="chart" data-chart='{...}'>              line chart, see Primer.chart below
     <pre class="mermaid">...</pre>                         Mermaid (loaded from the CDN only if present);
                                                            nodes named by a paper ID open its card
     $...$ / $$...$$ / \(...\) / \[...\]                     MathJax (loaded from the CDN only if math is present)
     <section class="updates"><article class="update">      timeline; all but the newest collapse, header badge
     h2 / h3 inside <main>                                  table of contents with scroll spy
   For widgets it exposes window.Primer: { svg, el, slider, chart, color, onTheme }. */
(function () {
  "use strict";
  const root = document.documentElement;
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const slug = document.body.dataset.slug || location.pathname.split("/").filter(Boolean).slice(-2, -1)[0] || "primer";
  const vaultName = document.body.dataset.vault || "PapersVault";
  let papers = {};
  let main = document.body;

  // ---- theme ------------------------------------------------------------
  const saved = store.get("primer-theme");
  if (saved) root.dataset.theme = saved;
  const isDark = () => root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  const themeHooks = [];
  const meta = document.querySelector("header.hero .meta");
  if (meta) {
    const b = document.createElement("button");
    b.className = "kit-btn"; b.type = "button"; b.textContent = isDark() ? "Light" : "Dark";
    b.onclick = () => {
      root.dataset.theme = isDark() ? "light" : "dark"; store.set("primer-theme", root.dataset.theme);
      b.textContent = isDark() ? "Light" : "Dark"; themeHooks.forEach(f => f(isDark()));
    };
    meta.appendChild(b);
  }
  const color = name => getComputedStyle(root).getPropertyValue("--" + name).trim();

  // ---- small helpers for hand-written widgets ----------------------------
  const NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs || {}) if (k === "text") n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function el(tag, attrs, parent) {
    const n = document.createElement(tag);
    for (const k in attrs || {}) if (k === "text") n.textContent = attrs[k]; else if (k === "html") n.innerHTML = attrs[k]; else n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  /* Primer.slider(controlsDiv, {label, min, max, step, value, fmt}, onInput) -> input element */
  function slider(parent, o, onInput) {
    const lab = el("label", {}, parent);
    lab.append(o.label + " ");
    const inp = el("input", { type: "range", min: o.min, max: o.max, step: o.step || "any", value: o.value }, lab);
    const out = el("output", {}, lab);
    const fmt = o.fmt || (v => (+v).toFixed(2));
    const upd = () => { out.textContent = fmt(+inp.value); onInput && onInput(+inp.value); };
    inp.addEventListener("input", upd); upd();
    return inp;
  }

  let tip = null;
  /* <figure class="chart" data-chart='{
        "title": "Share of papers about 3DGS", "unit": "%",
        "x": ["2024", "2025", "2026"],
        "series": [{"name": "CVPR", "values": [1.2, 3.4, 5.0]}, {"name": "ICLR", "values": [0.3, null, 1.1]}],
        "markers": [{"at": "2026", "label": "Update 1"}], "min": 0, "max": null }'>
        <figcaption>...</figcaption></figure>
     null = missing value (the line breaks). Markers draw a dashed vertical rule at an x label.
     "min" (default 0) / "max" (default: the data's max + 12%) fix the y range, e.g. 17-34 dB for PSNR. */
  function chart(fig, spec) {
    const W = 720, H = 300, L = 48, R = 16, T = 14, B = 46;
    const palette = ["s1", "s2", "s3", "s4", "s5", "s6"];
    const xs = spec.x || [], series = spec.series || [];
    const vals = series.flatMap(s => s.values.filter(v => v != null));
    const min = spec.min != null ? spec.min : 0;
    const top = spec.max != null ? spec.max : min + (Math.max(...vals, min) - min) * 1.12;
    const max = top > min ? top : min + 1;
    const x = i => L + (W - L - R) * (xs.length === 1 ? .5 : i / (xs.length - 1));
    const y = v => T + (H - T - B) * (1 - (v - min) / (max - min));
    fig.querySelectorAll(":scope > .legend, :scope > svg, :scope > .title").forEach(n => n.remove());
    const cap = fig.querySelector("figcaption");
    if (spec.title) fig.insertBefore(el("div", { class: "title", text: spec.title }), cap);
    const leg = el("div", { class: "legend" });
    leg.innerHTML = series.map((s, i) => `<span><i style="background:var(--${palette[i % 6]})"></i>${esc(s.name)}</span>`).join("");
    fig.insertBefore(leg, cap);
    const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": spec.title || "chart" });
    fig.insertBefore(g, cap);
    for (let k = 0; k <= 4; k++) {
      const v = min + (max - min) * k / 4, yy = y(v);
      svg("line", { x1: L, x2: W - R, y1: yy, y2: yy, stroke: "var(--line)" }, g);
      svg("text", { x: L - 8, y: yy + 4, "text-anchor": "end", "font-size": 11, fill: "var(--muted)", text: (v < 10 ? v.toFixed(1) : v.toFixed(0)) + (spec.unit || "") }, g);
    }
    xs.forEach((lab, i) => svg("text", { x: x(i), y: H - B + 20, "text-anchor": "middle", "font-size": 11, fill: "var(--muted)", text: lab }, g));
    (spec.markers || []).forEach(m => {
      const i = xs.indexOf(m.at); if (i < 0) return;
      svg("line", { x1: x(i), x2: x(i), y1: T, y2: H - B, stroke: "var(--accent)", "stroke-dasharray": "4 4" }, g);
      svg("text", { x: x(i) + 4, y: T + 10, "font-size": 11, fill: "var(--accent)", text: m.label || "" }, g);
    });
    series.forEach((s, si) => {
      const c = `var(--${palette[si % 6]})`;
      let d = "", pen = false;
      s.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? "L" : "M") + x(i) + " " + y(v); pen = true; });
      svg("path", { d, fill: "none", stroke: c, "stroke-width": 2.4, "stroke-linejoin": "round", "stroke-dasharray": s.dashed ? "6 4" : "none" }, g);
      s.values.forEach((v, i) => {
        if (v == null) return;
        const dot = svg("circle", { cx: x(i), cy: y(v), r: 4, fill: c, stroke: "var(--card)", "stroke-width": 1.5 }, g);
        dot.addEventListener("mousemove", e => {
          if (!tip) tip = el("div", { class: "kit-tip" }, document.body);
          tip.textContent = `${s.name} · ${xs[i]}: ${v}${spec.unit || ""}`; tip.style.display = "block"; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY - 28 + "px"; });
        dot.addEventListener("mouseleave", () => { if (tip) tip.style.display = "none"; });
      });
    });
    return g;
  }
  window.Primer = { svg, el, slider, chart: (fig, spec) => chart(fig, spec), color, isDark, onTheme: f => themeHooks.push(f), papers: {}, showPaper: id => showPaperFn(id) };
  let showPaperFn = () => {};
  // ---- CDN libraries, loaded only when the page uses them ---------------------------
  const load = (src, css) => new Promise((ok, bad) => {
    if (css) { el("link", { rel: "stylesheet", href: css }, document.head); }
    const s = el("script", { src, crossorigin: "anonymous" }); s.onload = ok; s.onerror = bad; document.head.appendChild(s);
  });
  // MathJax (SVG output): one script, no stylesheet or font files, follows currentColor in dark mode
  let mathP = null;
  const loadMath = () => mathP || (mathP = (() => {
    window.MathJax = {
      tex: { inlineMath: [["$", "$"], ["\\(", "\\)"]], displayMath: [["$$", "$$"], ["\\[", "\\]"]] },
      options: { skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code", "svg"] },
      svg: { fontCache: "global" },
      startup: { typeset: false },
    };
    return load("https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js").then(() => window.MathJax.startup.promise);
  })());

  // ---- tutor: ask Claude about what you are reading -----------------------------------------
  /* Uses the artifact runtime's `sample` capability (declare `capabilities: {sample: {}}` when
     publishing). Where it is unavailable (a local file, a viewer that declines) nothing is shown.
     Claude sees only what the page sends: the standing instructions, the reader's profile
     (a text/markdown script with id "learner", added by `vault.py cards` to the bundle), the current section's
     text and the paper cards it cites; `read_section` / `paper_card` let it look further. */
  const TUTOR_KEEP = 16;         // chat turns kept (the instructions turn is always kept)
  const SECTION_CHARS = 7000;    // section text sent per section
  async function initTutor() {
    if (!window.claude || typeof window.claude.use !== "function") return;
    // sample = asking Claude; db + user = the private chat archive; downloads = Markdown export
    const use = n => { try { return window.claude.use(n).catch(() => null); } catch (e) { return Promise.resolve(null); } };
    const [sample, db, userCap, dl] = await Promise.all(["sample", "db", "user", "downloads"].map(use));
    if (!sample) return;
    const uid = userCap ? await userCap.id().catch(() => null) : null;
    let chats = db && uid ? db.collection("data/users/" + uid) : null;   // private to this viewer
    let canTools = false;
    try { canTools = !!(await sample.limits()).tools; } catch (e) { canTools = false; }

    const title = (document.querySelector("header.hero h1") || {}).textContent || document.title;
    const learner = ((document.getElementById("learner") || {}).textContent || "").trim();
    const heads = () => [...main.querySelectorAll("h2[id], h3[id]")].filter(h => !h.closest("figure, aside, article.update, details"));
    const headTitle = h => { const c = h.cloneNode(true); c.querySelectorAll(".tutor-h, .progress").forEach(n => n.remove()); return c.textContent.trim(); };
    // the TeX source of a typeset formula (MathJax keeps it on its math items)
    const texOf = m => {
      try {
        const it = window.MathJax.startup.document.getMathItemsWithin(m)[0];
        return it ? (it.display ? `$$${it.math}$$` : `$${it.math}$`) : "";
      } catch (e) { return ""; }
    };
    const cleanText = node => {
      if (node.tagName && node.tagName.toLowerCase() === "mjx-container") return texOf(node) || "[formula]";   // a display formula
      if (node.querySelectorAll) node.querySelectorAll("mjx-container").forEach(m => { if (!m.dataset.tex) m.dataset.tex = texOf(m); });
      const c = node.cloneNode(true);
      if (c.querySelectorAll) c.querySelectorAll("script, style, svg, .tutor-h, .progress, mjx-container").forEach(n => {
        if (n.tagName.toLowerCase() === "mjx-container") n.replaceWith(document.createTextNode(n.dataset.tex || "[formula]"));
        else n.remove();   // drawings: their captions carry the meaning
      });
      return c.textContent.replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n\n").trim();
    };
    function sectionNodes(h) {
      const level = +h.tagName[1], out = [];
      for (let n = h.nextElementSibling; n; n = n.nextElementSibling) {
        if (/^H[1-3]$/.test(n.tagName) && +n.tagName[1] <= level) break;
        out.push(n);
      }
      return out;
    }
    function sectionText(h) {
      const t = sectionNodes(h).map(cleanText).filter(Boolean).join("\n\n");
      return t.length > SECTION_CHARS ? t.slice(0, SECTION_CHARS) + " [...]" : t;
    }
    function sectionOf(node) {
      let best = null;
      for (const h of heads()) {
        if (h === node || h.contains(node)) return h;
        if (h.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING) best = h; else break;
      }
      return best;
    }
    const cardsIn = h => {
      const ids = new Set();
      [h, ...sectionNodes(h)].forEach(n => n.querySelectorAll && n.querySelectorAll("a.paper[data-paper]").forEach(a => ids.add(a.dataset.paper)));
      return [...ids].filter(id => papers[id]).map(id => `[${id}] ${papers[id].title} (${papers[id].venue}): ${papers[id].contribution}`);
    };

    const RULES = [
      `You are a patient, expert tutor helping a researcher who is reading a primer page titled "${title}".`,
      "Explain from first principles: intuition first, then the precise idea. Use concrete examples and small numbers, and analogies when they really fit.",
      "Match the reader's background below: do not re-explain what they know, do not skip what they do not.",
      "Be concise: about 120-300 words unless asked to go deeper. One idea at a time. If the question is ambiguous, answer the most likely reading and say what you assumed.",
      "Formatting: plain paragraphs, short lists, **bold** for key terms, `code` for code. Math in LaTeX: $...$ inline, $$...$$ on its own line; explain every symbol in words after a formula.",
      "Papers: cite them as [PAPERID] (e.g. [CVPR20241019]) and only for the paper cards given to you; for any other work give its name and venue in plain text. Never invent what a paper says: the cards and section text are your evidence for specific papers; for general concepts use your own knowledge, and say so when you go beyond the page.",
      "When it helps, end with one short question that checks the reader's understanding. When asked to quiz, ask one question at a time and wait.",
      canTools ? "Tools: read_section(id) returns another section of the page; paper_card(id) returns a cited paper's card. Use them only when the current section is not enough." : "",
      learner ? `Reader profile:\n${learner}` : "Reader profile: not given.",
      "Page sections (id: title): " + heads().map(h => `${h.id}: ${headTitle(h)}`).join("; "),
    ].filter(Boolean).join("\n\n");

    const tools = !canTools ? undefined : [
      { name: "read_section", description: "Returns the text of one section of the page, by its id (see the section list). Use for context beyond the current section.",
        inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] },
        execute: ({ id }) => { const h = document.getElementById(String(id)); if (!h || !/^H[23]$/.test(h.tagName)) throw new Error("no such section"); return sectionText(h); } },
      { name: "paper_card", description: "Returns a cited paper's card (title, venue, authors, key contribution) by its ID, e.g. CVPR20241019.",
        inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] },
        execute: ({ id }) => { const p = papers[String(id)]; if (!p) throw new Error("not a paper cited on this page"); return { title: p.title, venue: p.venue_long, authors: p.authors, contribution: p.contribution }; } },
    ];

    // ---- state -----------------------------------------------------------------------
    /* turns: [{role, content, show?, quote?, carried?, sectionTitle?, note?}]; content is what Claude
       sees, carried = the section whose text that turn sent. With the archive, each chat is one
       document data/users/<uid>/chat-... (saved after every answer; this browser only remembers which
       chat is open). Without it, the open chat lives in this browser's storage. */
    const KEY = `${slug}:tutor`;
    const DOC_MAX = 240000;       // a db document holds at most 256 KiB
    let turns = [], chatId = null, created = null, full = false, writeQ = Promise.resolve();
    let quote = "", focus = null, ctl = null;
    const newId = () => "chat-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
    const local = () => { try { return JSON.parse(store.get(KEY) || "null") || {}; } catch (e) { return {}; } };
    const remember = () => { try { store.set(KEY, JSON.stringify(chats ? { chatId } : { turns: turns.slice(-TUTOR_KEEP) })); } catch (e) {} };
    const storable = () => turns.map((t, i) => {
      const o = { role: t.role, content: t.content };
      ["show", "quote", "carried", "sectionTitle", "note"].forEach(k => { if (t[k]) o[k] = t[k]; });
      if (t.role === "user" && i < turns.length - TUTOR_KEEP) o.content = t.show || t.content;   // context never sent again
      return o;
    });
    function chatBody() {
      const first = turns.find(t => t.role === "user") || {}, now = new Date().toISOString();
      created = created || now;
      return { kind: "chat", slug, page: title, title: String(first.show || "").slice(0, 100), section: first.sectionTitle || "",
               created, updated: now, n: turns.length, turns: storable() };
    }
    function save() {
      remember();
      if (!chats || !turns.length || full) return;
      if (!chatId) { chatId = newId(); remember(); }
      const body = chatBody();
      if (JSON.stringify(body).length > DOC_MAX) { full = true; status("This chat is full, so new messages are no longer archived: start a new chat."); return; }
      const ref = chats.doc(chatId);
      const write = () => ref.set(body);
      writeQ = writeQ.then(write).catch(e => {
        const code = e && e.code;
        if (code === "unavailable") return new Promise(r => setTimeout(r, 800 + Math.random() * 800)).then(write).catch(() => status("Could not save this chat; it will be saved with the next answer."));
        if (code === "quota_exceeded") status("The archive is full: delete some old chats to keep saving.");
        else if (["revoked", "not_granted", "capability_disabled", "capability_removed", "invalid_argument"].includes(code)) { disableArchive(); status("Chats can't be archived in this view; this one is kept in this browser only."); }
        else status("Could not save this chat; it will be saved with the next answer.");
      });
    }
    function loadChat(id, data) {
      if (ctl) ctl.abort();
      chatId = id; created = data.created || null; full = false;
      turns = (Array.isArray(data.turns) ? data.turns : []).map(t => Object.assign({}, t));
      remember(); renderLog();
    }

    // ---- UI ----------------------------------------------------------------------------
    const panel = el("aside", { id: "tutor", role: "complementary", "aria-label": "Tutor" }, document.body);
    panel.innerHTML = `<div class="tutor-head"><b>Tutor</b><span class="ctx"></span><button type="button" data-a="archive">Archive</button><button type="button" data-a="new">New chat</button><button type="button" data-a="close" aria-label="Close">&times;</button></div>
      <div class="tutor-status"></div>
      <div class="tutor-archive"></div>
      <div class="tutor-log" aria-live="polite"></div>
      <div class="tutor-quote"><button type="button" aria-label="Remove quote">&times;</button><span></span></div>
      <div class="tutor-chips"></div>
      <form class="tutor-form"><textarea rows="2" placeholder="Ask about this page..."></textarea><button type="submit">Ask</button></form>`;
    const log = panel.querySelector(".tutor-log"), ctxEl = panel.querySelector(".ctx"), box = panel.querySelector("textarea"),
          sendBtn = panel.querySelector(".tutor-form button"), quoteEl = panel.querySelector(".tutor-quote"), chips = panel.querySelector(".tutor-chips");
    [["Explain in more depth", "Explain this in more depth."], ["Simpler, with an analogy", "Explain this more simply, with an analogy."],
     ["Show the math", "Walk me through the math step by step, explaining every symbol."], ["Concrete example", "Give me a concrete worked example with small numbers."],
     ["Why does it matter?", "Why does this matter? What would break or be worse without it?"], ["Quiz me", "Quiz me on this: ask me one question, then wait for my answer."]]
      .forEach(([label, q]) => { const b = el("button", { type: "button", text: label }, chips); b.onclick = () => ask(q); });

    const setCtx = () => { ctxEl.textContent = focus ? "· " + headTitle(focus) : ""; };
    const setQuote = q => { quote = (q || "").trim().slice(0, 1500); quoteEl.querySelector("span").textContent = quote ? "“" + (quote.length > 220 ? quote.slice(0, 220) + "…" : quote) + "”" : ""; quoteEl.classList.toggle("on", !!quote); };
    quoteEl.querySelector("button").onclick = () => setQuote("");
    function open(h, q) {
      if (h) focus = h;
      if (!focus) focus = sectionOf(document.elementFromPoint(innerWidth / 2, innerHeight / 3) || main) || heads()[0] || null;
      setCtx(); if (q !== undefined) setQuote(q);
      panel.classList.add("open"); document.body.classList.add("tutor-open");
      setTimeout(() => box.focus(), 50);
    }
    const close = () => { panel.classList.remove("open"); document.body.classList.remove("tutor-open"); if (ctl) ctl.abort(); };
    panel.querySelector('[data-a="close"]').onclick = close;
    panel.querySelector('[data-a="new"]').onclick = () => { if (ctl) ctl.abort(); turns = []; chatId = null; created = null; full = false; remember(); showArchive(false); renderLog(); };
    const statusEl = panel.querySelector(".tutor-status");
    function status(msg) { statusEl.textContent = msg || ""; statusEl.classList.toggle("on", !!msg); }

    // ---- archive: every chat, newest first; open (and continue), export to Markdown, delete ----
    const arch = panel.querySelector(".tutor-archive"), archBtn = panel.querySelector('[data-a="archive"]');
    function disableArchive() { chats = null; archBtn.remove(); showArchive(false); }
    if (!chats) archBtn.remove();
    const when = iso => { try { return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch (e) { return ""; } };
    function toMarkdown(c) {
      const obs = t => String(t).replace(/\[([A-Z]+\d{8})\]/g, (m, id) => papers[id] ? `[[${id}|${papers[id].short}]]` : `[[${id}]]`);
      const out = ["---", `primer: ${c.page || title}`, `slug: ${c.slug || slug}`, `section: ${JSON.stringify(c.section || "")}`,
                   `created: ${c.created || ""}`, `updated: ${c.updated || ""}`, "---", "", `# ${c.title || "Tutor chat"}`, ""];
      (c.turns || []).forEach(t => {
        if (t.role === "user") {
          out.push("**You**" + (t.sectionTitle ? ` _(in "${t.sectionTitle}")_` : "") + ":");
          if (t.quote) out.push("", "> " + String(t.quote).replace(/\n/g, "\n> "));
          out.push("", String(t.show || t.content), "");
        } else out.push("**Tutor:**", "", obs(t.content), t.note ? `\n_${t.note}_` : "", "");
      });
      return out.join("\n");
    }
    async function exportChat(c, btn) {
      const name = `${slug}-${String(c.created || "").slice(0, 10)}-${String(c.title || "chat").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)}.md`;
      try { await dl.save({ filename: name, data: toMarkdown(c) }); }
      catch (e) { if (e && e.code === "unavailable") btn.remove(); else if (e && e.code !== "declined") status("Could not export that chat."); }
    }
    async function showArchive(on) {
      panel.classList.toggle("archive-on", !!on);
      archBtn.textContent = on ? "Back to chat" : "Archive";
      if (!on || !chats) return;
      arch.innerHTML = '<div class="tutor-empty">Loading your chats...</div>';
      let list = [];
      try {
        await writeQ;   // include the chat that is being saved right now
        list = (await chats.where("kind", "==", "chat").orderBy("updated", "desc").limit(100).get()).docs.map(d => ({ id: d.id, ...d.data() }));
      } catch (e) { arch.innerHTML = ""; el("div", { class: "tutor-empty", text: "Could not load the archive. Try again in a moment." }, arch); return; }
      arch.innerHTML = "";
      if (!list.length) { el("div", { class: "tutor-empty", text: "No archived chats yet. Every chat is saved here automatically, privately, after each answer." }, arch); return; }
      el("div", { class: "tutor-empty", text: `${list.length} chat${list.length > 1 ? "s" : ""}, private to you. Open one to read or continue it.` }, arch);
      list.forEach(c => {
        const row = el("div", { class: "tutor-item" + (c.id === chatId ? " current" : "") }, arch);
        el("div", { class: "t", text: (c.title || "Untitled chat") + (c.id === chatId ? "  (open now)" : "") }, row);
        el("div", { class: "m", text: [c.section, when(c.updated), `${c.n || (c.turns || []).length} messages`].filter(Boolean).join(" · ") }, row);
        const act = el("div", { class: "a" }, row);
        el("button", { type: "button", text: "Open" }, act).onclick = () => { loadChat(c.id, c); showArchive(false); };
        if (dl) { const b = el("button", { type: "button", text: "Export .md" }, act); b.onclick = () => exportChat(c, b); }
        const del = el("button", { type: "button", text: "Delete" }, act);
        del.onclick = async () => {
          if (!del.dataset.armed) { del.dataset.armed = "1"; del.textContent = "Really delete?"; setTimeout(() => { delete del.dataset.armed; del.textContent = "Delete"; }, 4000); return; }
          del.disabled = true;
          try {
            await chats.doc(c.id).delete();
            if (c.id === chatId) { turns = []; chatId = null; created = null; remember(); renderLog(); }
            row.remove();
          } catch (e) { del.disabled = false; status("Could not delete that chat."); }
        };
      });
    }
    archBtn.onclick = () => showArchive(!panel.classList.contains("archive-on"));
    document.addEventListener("keydown", e => { if (e.key === "Escape" && panel.classList.contains("open") && !document.getElementById("kit-card")?.classList.contains("open")) close(); });

    // markdown-lite -> HTML; math is protected first and typeset by MathJax afterwards
    function md(src) {
      const math = [];
      let s = String(src).replace(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$/g, m => { math.push(m); return `\u0000${math.length - 1}\u0000`; });
      s = esc(s);
      s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*\w])\*([^*\n]+)\*(?=[^*\w]|$)/g, "$1<em>$2</em>");
      s = s.replace(/\[([A-Z]+\d{8})\]/g, (m, id) => papers[id] ? `<a class="paper" data-paper="${id}" href="#${id}" title="${esc(papers[id].title)}">${esc(papers[id].short)}<span class="v">${esc(papers[id].venue)}</span></a>` : m);
      const blocks = s.split(/\n{2,}/).map(b => {
        const lines = b.split("\n");
        if (lines.every(l => /^\s*[-*] /.test(l))) return "<ul>" + lines.map(l => "<li>" + l.replace(/^\s*[-*] /, "") + "</li>").join("") + "</ul>";
        if (lines.every(l => /^\s*\d+[.)] /.test(l))) return "<ol>" + lines.map(l => "<li>" + l.replace(/^\s*\d+[.)] /, "") + "</li>").join("") + "</ol>";
        if (/^#{1,4} /.test(b)) return "<p><strong>" + b.replace(/^#{1,4} /, "") + "</strong></p>";
        return "<p>" + lines.join("<br>") + "</p>";
      });
      return blocks.join("").replace(/\u0000(\d+)\u0000/g, (m, i) => esc(math[+i]));
    }
    const typeset = node => { if (/\$|\\\(|\\\[/.test(node.textContent)) loadMath().then(() => window.MathJax.typesetPromise([node])).catch(() => {}); };
    function bubble(t) {
      const b = el("div", { class: "tutor-msg " + (t.role === "user" ? "user" : "bot") }, log);
      if (t.role === "user") {
        if (t.quote) el("blockquote", { text: t.quote.length > 300 ? t.quote.slice(0, 300) + "…" : t.quote }, b);
        el("div", { text: t.show || t.content }, b);
      } else { b.innerHTML = md(t.content); if (t.note) el("div", { class: "note", text: t.note }, b); typeset(b); }
      return b;
    }
    function renderLog() {
      log.innerHTML = "";
      if (!turns.length) el("div", { class: "tutor-empty", text: "Select a passage and press “Ask about this”, use the Ask button next to a heading, or type a question. Answers use your own Claude account." }, log);
      turns.forEach(bubble); log.scrollTop = log.scrollHeight;
    }
    const busy = on => { sendBtn.textContent = on ? "Stop" : "Ask"; sendBtn.classList.toggle("stop", on); box.disabled = on; chips.querySelectorAll("button").forEach(b => { b.disabled = on; }); };
    const COPY = { rate_limited: "Too many questions for now, or your usage limit was reached. Try again in a bit.", session_expired: "Please sign in to Claude again.",
                   refused: "Claude declined to answer that. Try rephrasing.", empty_completion: "No answer came back. Try asking in a different way.",
                   prompt_too_large: "The conversation got too long. Start a new chat." };

    async function ask(question) {
      question = String(question || "").trim();
      if (!question || ctl) return;
      if (!panel.classList.contains("open")) open();
      showArchive(false); status("");
      const h = focus;
      let content = "", carried;
      // send a section's text once per conversation window (older turns are dropped as the chat grows)
      if (h && !turns.slice(-(TUTOR_KEEP - 2)).some(t => t.carried === h.id)) {
        const cards = cardsIn(h);
        content += `[The reader is in the section "${headTitle(h)}" (id ${h.id}). Its text:]\n${sectionText(h)}\n\n` +
                   (cards.length ? `[Paper cards cited in this section:]\n${cards.join("\n")}\n\n` : "");
        carried = h.id;
      } else if (h) content += `[The reader is in the section "${headTitle(h)}".]\n\n`;
      if (quote) content += `[The reader selected this passage:]\n"${quote}"\n\n`;
      content += `[Question:] ${question}`;
      const userTurn = { role: "user", content, show: question, quote, carried, sectionTitle: h ? headTitle(h) : "" };
      turns.push(userTurn); setQuote(""); box.value = "";
      if (log.querySelector(".tutor-empty")) log.innerHTML = "";
      bubble(userTurn);
      const out = el("div", { class: "tutor-msg bot thinking", text: "Thinking..." }, log);
      log.scrollTop = log.scrollHeight;
      // drop the oldest turns (never the instructions); the list must start and end on a user turn
      let hist = turns.slice(-TUTOR_KEEP);
      while (hist.length && hist[0].role !== "user") hist = hist.slice(1);
      const input = [{ role: "user", content: RULES }, ...hist.map(t => ({ role: t.role, content: t.content }))];
      ctl = new AbortController(); busy(true);
      let partial = "";
      try {
        const r = await sample(input, { signal: ctl.signal, cache: false, ...(tools ? { tools } : {}),
          onText: ({ text }) => { partial = text; out.classList.remove("thinking"); out.innerHTML = md(text); log.scrollTop = log.scrollHeight; } });
        const t = { role: "assistant", content: r.text, note: r.truncated ? "Cut short: ask for less at a time." : "" };
        turns.push(t); out.innerHTML = md(r.text); if (t.note) el("div", { class: "note", text: t.note }, out); typeset(out);
      } catch (e) {
        const code = e && e.code;
        const kept = code === "refused" ? "" : (e && e.text) || partial;
        if (["not_granted", "sampling_disabled", "not_declared", "capability_disabled", "capability_removed"].includes(code)) {
          turns.pop(); out.remove(); teardown(); return;
        }
        out.classList.remove("thinking");
        out.innerHTML = kept ? md(kept) : "";
        if (kept) { turns.push({ role: "assistant", content: kept, note: "(interrupted)" }); typeset(out); } else turns.pop();
        if (code !== "cancelled") el("div", { class: "note", text: COPY[code] || "Something went wrong. You can ask again." }, out);
        else if (!kept) out.remove();
      } finally { ctl = null; busy(false); save(); box.focus(); }
    }
    panel.querySelector(".tutor-form").addEventListener("submit", e => { e.preventDefault(); if (ctl) ctl.abort(); else ask(box.value); });
    box.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!ctl) ask(box.value); } });

    // entry points: header button, a button on each heading, "Ask about this" on a text selection
    const hb = meta && el("button", { class: "kit-btn", type: "button", text: "Ask the tutor" }, null);
    if (hb) { meta.insertBefore(hb, meta.querySelector(".kit-btn")); hb.onclick = () => open(); }
    heads().forEach(h => { const b = el("button", { class: "tutor-h", type: "button", text: "Ask", title: "Ask the tutor about this section" }, h);
      b.onclick = e => { e.preventDefault(); open(h, ""); }; });
    const pop = el("button", { class: "tutor-ask", type: "button", text: "Ask about this" }, document.body);
    let popSel = null;
    document.addEventListener("selectionchange", () => {
      const sel = getSelection();
      const txt = sel && !sel.isCollapsed ? sel.toString().trim() : "";
      if (!txt || txt.length > 3000 || !main.contains(sel.anchorNode) || panel.contains(sel.anchorNode)) { pop.style.display = "none"; return; }
      const r = sel.getRangeAt(0).getBoundingClientRect();
      pop.style.left = Math.max(8, Math.min(innerWidth - 140, r.left + r.width / 2 - 55 + scrollX)) + "px";
      pop.style.top = (r.bottom + scrollY + 8) + "px";
      pop.style.display = "block"; popSel = { txt, node: sel.anchorNode };
    });
    pop.addEventListener("mousedown", e => e.preventDefault());   // keep the selection
    pop.onclick = () => { if (!popSel) return; pop.style.display = "none"; open(sectionOf(popSel.node.nodeType === 1 ? popSel.node : popSel.node.parentElement), popSel.txt); };
    function teardown() { close(); panel.remove(); pop.remove(); if (hb) hb.remove(); main.querySelectorAll(".tutor-h").forEach(b => b.remove()); }
    // reopen the chat that was open last time in this browser
    const last = local();
    if (chats && last.chatId) {
      try { const snap = await chats.doc(last.chatId).get(); if (snap.exists) loadChat(last.chatId, snap.data()); } catch (e) {}
    } else if (!chats && Array.isArray(last.turns)) turns = last.turns;
    renderLog();
    window.Primer.tutor = { open, ask, showArchive, get chatId() { return chatId; } };
  }
  function init() {
    try { papers = JSON.parse((document.getElementById("papers") || {}).textContent || "{}"); } catch (e) { console.warn("papers JSON", e); }
    Object.assign(window.Primer.papers, papers);
    main = document.querySelector("main") || document.body;
    // ---- paper chips + card --------------------------------------------------
    const card = el("aside", { id: "kit-card", role: "dialog", "aria-live": "polite" }, document.body);
    card.innerHTML = '<button class="close" aria-label="Close">&times;</button><div class="body"></div>';
    card.querySelector(".close").onclick = () => card.classList.remove("open");
    document.addEventListener("keydown", e => { if (e.key === "Escape") card.classList.remove("open"); });
    function showPaper(id) {
      const p = papers[id]; if (!p) return;
      const obs = `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(String(p.note || "").replace(/\.md$/, ""))}`;
      card.querySelector(".body").innerHTML =
        `<h4>${esc(p.title)}</h4><div class="sub">${esc(p.authors)} &middot; ${esc(p.venue_long)} &middot; ${esc(id)}` +
        (p.built_on_by ? ` &middot; built on by ${p.built_on_by} vault papers` : "") + `</div><p>${esc(p.contribution)}</p>` +
        `<div class="actions">` + (p.pdf ? `<a href="${esc(p.pdf)}" target="_blank" rel="noopener">PDF</a>` : "") +
        (p.code ? `<a href="${esc(p.code)}" target="_blank" rel="noopener">Code</a>` : "") +
        `<a href="${obs}">Open note in Obsidian</a></div>`;
      card.classList.add("open");
    }
    showPaperFn = showPaper;
    document.querySelectorAll("a.paper[data-paper]").forEach(a => {
      const p = papers[a.dataset.paper];
      if (!a.textContent.trim()) a.textContent = p ? p.short : a.dataset.paper;
      if (!p) { a.classList.add("missing"); a.title = a.dataset.paper + " (not in vault.db: run vault.py cards)"; return; }
      a.title = p.title;
      if (!a.querySelector(".v") && !a.hasAttribute("data-novenue")) a.insertAdjacentHTML("beforeend", `<span class="v">${esc(p.venue)}</span>`);
      a.href = "#" + a.dataset.paper;
    });
    document.addEventListener("click", e => {
      const a = e.target.closest && e.target.closest("a.paper[data-paper]");
      if (a && papers[a.dataset.paper]) { e.preventDefault(); showPaper(a.dataset.paper); }
    });

    // ---- table of contents ---------------------------------------------------
    const toc = document.querySelector("nav.toc");
    const used = {};
    const heads = [...main.querySelectorAll("h2, h3")].filter(h => !h.closest("figure, aside, article.update, details"));
    heads.forEach(h => {
      if (!h.id) {
        let id = h.textContent.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "section";
        while (used[id] || document.getElementById(id)) id += "-";
        h.id = id;
      }
      used[h.id] = 1;
      if (toc) { const a = el("a", { href: "#" + h.id, class: h.tagName.toLowerCase() }, toc); a.textContent = h.dataset.toc || h.textContent; }
    });
    if (toc && "IntersectionObserver" in window) {
      const links = [...toc.querySelectorAll("a")];
      const spy = new IntersectionObserver(es => es.forEach(e => {
        if (e.isIntersecting) links.forEach(a => a.classList.toggle("active", a.hash === "#" + e.target.id));
      }), { rootMargin: "0px 0px -70% 0px" });
      heads.forEach(h => spy.observe(h));
    }

    // ---- reading path ----------------------------------------------------------
    document.querySelectorAll("ul.reading").forEach(list => {
      const items = [...list.children].filter(li => li.tagName === "LI");
      items.forEach(li => {
        const key = `${slug}:read:${li.dataset.paper || (li.querySelector("a.paper") || {}).dataset?.paper || li.textContent.trim().slice(0, 60)}`;
        const body = el("div"); while (li.firstChild) body.appendChild(li.firstChild);
        const box = el("input", { type: "checkbox", "aria-label": "read" });
        li.append(box, body);
        box.checked = store.get(key) === "1"; li.classList.toggle("done", box.checked);
        box.addEventListener("change", () => { store.set(key, box.checked ? "1" : "0"); li.classList.toggle("done", box.checked); progress(); });
      });
      function progress() {
        let h = list.previousElementSibling; while (h && !/^H[2-4]$/.test(h.tagName)) h = h.previousElementSibling;
        if (!h) return;
        let span = h.querySelector(".progress"); if (!span) span = el("span", { class: "progress" }, h);
        span.textContent = `${items.filter(li => li.classList.contains("done")).length} / ${items.length} read`;
      }
      progress();
    });

    // ---- updates timeline --------------------------------------------------------
    const updates = [...document.querySelectorAll("article.update")];
    updates.forEach((u, i) => {
      const hd = u.querySelector(":scope > header");
      if (i > 0) u.classList.add("collapsed");
      if (hd) hd.addEventListener("click", () => u.classList.toggle("collapsed"));
    });
    if (updates.length && meta) {
      const sec = updates[0].closest("section") || updates[0];
      if (!sec.id) sec.id = "updates";
      const last = updates.map(u => u.dataset.date || "").sort().pop();
      const badge = el("a", { class: "badge", href: "#" + sec.id }, null);
      badge.textContent = `Updated ${last ? last.slice(0, 7) : ""} · ${updates.length} update${updates.length > 1 ? "s" : ""}`;
      meta.insertBefore(badge, meta.firstChild);
    }

    // ---- charts --------------------------------------------------------------------
    document.querySelectorAll("figure.chart[data-chart]").forEach(fig => {
      try { chart(fig, JSON.parse(fig.dataset.chart)); } catch (e) { fig.insertAdjacentHTML("afterbegin", `<p class="muted">chart spec error: ${esc(e.message)}</p>`); }
    });

    if (/\$\$|\\\(|\\\[|\$[^$\s][^$]*\$/.test(main.textContent)) {
      loadMath().then(() => window.MathJax.typesetPromise([main])).catch(() => console.warn("MathJax could not be loaded (offline?)"));
    }
    const mermaids = [...document.querySelectorAll("pre.mermaid")];
    if (mermaids.length) {
      mermaids.forEach(m => { m.dataset.src = m.textContent; });
      const draw = () => {
        mermaids.forEach(m => { m.removeAttribute("data-processed"); m.innerHTML = ""; m.textContent = m.dataset.src; });
        window.mermaid.initialize({ startOnLoad: false, theme: isDark() ? "dark" : "neutral", securityLevel: "strict",
                                    flowchart: { useMaxWidth: false, htmlLabels: true } });
        window.mermaid.run({ nodes: mermaids }).then(() => mermaids.forEach(m => m.querySelectorAll("g.node").forEach(g => {
          const id = ((g.id || "").match(/([A-Z]+\d{8})/) || [])[1];
          if (id && papers[id]) { g.addEventListener("click", () => showPaper(id)); svg("title", { text: papers[id].title }, g); }
        }))).catch(e => console.error(e));
      };
      load("https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js").then(() => { draw(); themeHooks.push(draw); })
        .catch(() => mermaids.forEach(m => m.insertAdjacentHTML("beforebegin", '<p class="muted small">Mermaid could not be loaded (offline?); the graph source follows.</p>')));
    }

    initTutor().catch(e => console.warn("tutor", e));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
