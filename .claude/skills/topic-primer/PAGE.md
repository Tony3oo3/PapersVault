# Building the primer page

The page is written by hand for each topic. There is no generator: the content decides the
layout and the pictures. A shared kit in `research_topics/_kit/` handles the parts every page
needs, so the effort goes into explanation and visuals:
- theme, typography and table of contents;
- paper chips and cards;
- reading checkboxes, quiz boxes, the updates timeline;
- charts, Mermaid and MathJax.

If the harness offers the `artifact-design`, `artifact-diagramming` or `dataviz` skills, load
them before building the page: their guidance on diagrams and charts applies here.

## Skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>3D Gaussian Splatting</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Source+Serif+4:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../_kit/primer.css">
</head>
<body data-slug="3d-gaussian-splatting" data-vault="PapersVault">
<header class="hero"><div class="wrap">
  <div class="kicker">Research primer · PapersVault</div>
  <h1>3D Gaussian Splatting</h1>
  <p class="lede">One or two sentences: what it is and why you should care.</p>
  <div class="meta"><span>For a CV researcher who knows NeRF</span><span>2,741 papers, CVPR'24-ICML'26</span><span>vault.db 2026-10-16</span></div>
</div></header>
<div class="layout">
<nav class="toc"></nav>
<main>
  <div class="tldr">...the mental model...</div>
  <h2 id="prereqs">What you need first</h2>
  ...
</main>
</div>
<script src="../_kit/primer.js"></script>
<script>
  /* this page's widgets: they come after the kit, so window.Primer exists */
</script>
<script id="papers" type="application/json">{}</script>
</body>
</html>
```

Keep the kit references exactly as `../_kit/primer.css` and `../_kit/primer.js`:
`vault.py cards` inlines them into `.bundle.html` for publishing. The kit loads Mermaid
(`<pre class="mermaid">`) and MathJax (`$...$`, `$$...$$`) from the CDN only when the page uses
them.

## Building blocks (all in the kit)

| Markup | Use |
|---|---|
| `<div class="tldr">` | the mental model at the top |
| `<div class="callout intuition\|math\|example\|opinion\|warn\|recall">`, optional `data-label="..."` | intuition, a derivation, a worked example, your opinion ("My read"), a pitfall, "you already know this" |
| `<div class="steps"><div>...</div>...</div>` | numbered pipeline stages |
| `<div class="compare"><div><h4>A</h4>...</div><div><h4>B</h4>...</div></div>` | side-by-side contrast (NeRF vs 3DGS, before vs after) |
| `<figure class="diagram">` + inline `<svg>` + `<figcaption>` | a hand-drawn diagram |
| `<figure class="widget">` + `<svg>` + `<div class="controls">` | an interactive figure |
| `<figure class="paperfig"><img src="figs/..."><figcaption>` | a real figure from a paper |
| `<figure class="chart" data-chart='{...}'>` | line chart (spec in `primer.js`: `x`, `series`, `unit`, `markers`) |
| `<pre class="mermaid">` | the lineage graph; nodes named by paper ID open the card |
| `<a class="paper" data-paper="ID">Name</a>` | paper chip |
| `<ul class="reading"><li data-paper="ID">...` | reading path with persistent checkboxes |
| `<details class="quiz"><summary>Question</summary>key points</details>` | quiz |
| `<section class="updates"><article class="update" data-date="...">` | update timeline (newest first) |
| (nothing to write) | the **tutor**: an "Ask the tutor" button, an "Ask" button on every `h2`/`h3`, and "Ask about this" on a text selection. It opens a chat panel that answers with the reader's own Claude account, using the section's text, the paper cards and the reader's profile. It needs the Artifact's `sample` capability, so it appears only in the published page. With `db` + `user` (+ `downloads`) it also keeps a private **archive** of every chat (open, continue, export to Markdown, delete). Give every `h2`/`h3` an `id`: the tutor uses them to name and fetch sections |
| `.fig-row`, `figure.bleed`, `.muted`, `.small` | layout helpers |

## Visuals: the point of the page

Every key concept gets a picture that shows **the actual mechanism**, not boxes with labels.
Ask: what would I draw on a whiteboard to explain this? Then draw that.

| The concept is... | Draw |
|---|---|
| a geometric object or a transformation | an SVG of the object; a slider for the parameter that matters (covariance → stretched, rotated ellipse; a projection; a warp) |
| a process over time or iterations | a stepped animation with play/step buttons (densification, a denoising trajectory, an optimisation) |
| an algorithm with an order | numbered panels, or a small simulation (front-to-back alpha compositing that stops when transmittance saturates) |
| a comparison of two approaches | a `.compare` block, or one diagram drawn twice with the difference highlighted |
| a trade-off | a 2D plot of the trade-off with the methods placed on it (speed vs quality, from the notes' numbers) |
| a pipeline | an SVG flow showing the tensors and shapes passed between stages, not just the stage names |
| how the field grew | the lineage Mermaid, plus the trend `figure.chart` |
| what a method's output looks like | the paper's own teaser or result figure |

Rules:
- **SVG**: make the `<svg>` a direct child of its `<figure>` (the kit sizes only `figure > svg`, so
  math in captions keeps its size), set `viewBox` and no fixed width (the kit scales it). Colours only through the
  tokens (`var(--fg)`, `var(--muted)`, `var(--line)`, `var(--accent)`, `var(--s1)` ...
  `var(--s6)`), so dark mode works. Text without a `fill` gets `var(--fg)` from the kit; a
  `fill` attribute or style wins. Label things directly instead of using a legend. One idea per
  figure.
- **Phones**: an SVG shrinks with the column, to roughly 0.55x at 390 px for a 700-wide viewBox,
  so 12-unit text becomes ~7 px. Keep diagrams narrow: a viewBox of about 480-560 wide, with
  text of 15-16 units. Stack panels vertically rather than side by side, or draw two
  `<svg>` (wide and narrow) and switch them with a media query. Few words inside a diagram;
  the explanation goes in the caption and the prose.
- **Arrowheads and gradients**: `<marker>`/`<linearGradient>` ids are global to the page, so
  give each figure its own prefix (`fig3-arrow`).
- **Widgets**: vanilla JS in the page's script after the kit, with no build step and no
  libraries beyond the kit. Use `Primer.svg(tag, attrs, parent)` and
  `Primer.slider(controls, {label, min, max, step, value, fmt}, onInput)`. Redraw from state on
  each input. If colours are read in JS, re-read them in `Primer.onTheme(...)`. Keep each
  widget to roughly 30-80 lines. Every widget must also make sense as a static picture: draw
  its initial state immediately.
- **Paper figures**: take them from the OCR images (`vault.py ocr ID --path-only`, then
  `imgs/` next to the .md: JPEG crops of each printed figure, sometimes split in pieces), or
  from the vault's own `{CONF}{YEAR}/imgs/{ID}/` (WebP teaser and method figures, local only).
  Look at a figure with Read before using it. Copy it into `figs/` as WebP, max 1400 px wide,
  under ~300 KB, using the PaperMiner venv's Pillow:
  `../.venv/bin/python -c "from PIL import Image; im=Image.open('SRC'); im.thumbnail((1400,1400)); im.save('research_topics/<slug>/figs/NAME.webp', quality=85)"`.
  Caption it with what to look at and the paper chip ("Figure 2 of <chip>").
- **Charts**: `figure.chart` for shares over time. Years on x, one series per venue family. A
  dashed series (`"dashed": true`) for a definition that is less precise. Update markers come
  from `markers`. `"min"`/`"max"` fix the y range: a PSNR chart starting at 0 wastes half its
  height.
- **Lineage graph**: paste the Mermaid body of `vault.py lineage` without the ```mermaid fences
  and `<!-- -->` lines into `<pre class="mermaid">`. Escape its `<br/>` as `&lt;br/&gt;`:
  inside HTML the browser would turn it into an element and Mermaid would never see it.
- **Math**: inline `$...$`, display `$$...$$`. Explain every symbol in words right after a
  formula.
- Aim for 6-12 visuals in a standard primer, at least 2 of them interactive, and at least one
  real paper figure.

## Before you call it done

1. `vault.py cards <slug>`: no missing chips, no broken local links.
2. Check that each inline script parses:
   `node -e "const fs=require('fs');const h=fs.readFileSync('research_topics/<slug>/index.html','utf8');for(const m of h.matchAll(/<script>([\s\S]*?)<\/script>/g)) new Function(m[1]);console.log('ok')"`.
3. If a browser tool is available (Claude in Chrome, Playwright), open the page. Check it at
   ~390 px wide and at desktop width, in light and dark mode. Every widget must respond, no
   text may overflow, and no horizontal page scroll may appear. If none is available, say the
   page was not checked visually.
4. Read the page once as the learner would. Every section must explain before it cites, and
   every concept must have its picture.
