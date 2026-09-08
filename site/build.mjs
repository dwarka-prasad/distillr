// Builds the Distillr site into site/dist: landing + docs pages rendered from the repo's markdown.
import { marked } from "marked";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.join(root, "site", "dist");
mkdirSync(path.join(out, "docs"), { recursive: true });
const BASE = "/distillr";
const version = readFileSync(path.join(root, "pyproject.toml"), "utf8").match(/^version\s*=\s*"([^"]+)"/m)?.[1] ?? "";

const pages = [
  { slug: "readme", title: "Guide", file: "README.md" },
  { slug: "results", title: "Benchmark results", file: "benchmarks/RESULTS.md" },
  { slug: "spec", title: "Specification", file: "docs/spec.md" },
  { slug: "design", title: "Design notes", file: "docs/design.md" },
  { slug: "roadmap", title: "Roadmap", file: "ROADMAP.md" },
  { slug: "contributing", title: "Contributing", file: "CONTRIBUTING.md" },
  { slug: "changelog", title: "Changelog", file: "CHANGELOG.md" },
];
marked.use({ gfm: true });
const css = readFileSync(path.join(root, "site", "site.css"), "utf8");
const nav = pages.map((p) => `<a href="${BASE}/docs/${p.slug}.html" data-slug="${p.slug}">${p.title}</a>`).join("");
const favicon = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#7c3aed"/><path d="M6 6h12M8 12h8M10 18h4" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/></svg>');

const shell = (title, body, { slug = "", docs = true } = {}) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title} · Distillr</title><meta name="description" content="Distillr: a unified compression pipeline for LLM inputs. Trim irrelevant data, encode the rest in the cheapest lossless format, and account for every token saved. 95% fewer tokens on realistic payloads with 100% needle recall.">
<meta property="og:title" content="${title} · Distillr"><meta property="og:description" content="Cut LLM token spend without silently dropping what the model needed.">
<link rel="icon" href="${favicon}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>${css}</style>
<script>(function(){try{var t=localStorage.getItem("distillr_theme")||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");document.documentElement.setAttribute("data-theme",t)}catch(e){}})();</script>
</head><body class="${docs ? "docs" : "landing"}">
<header class="top"><a class="brand" href="${BASE}/"><span class="logo"></span>Distillr <span class="ver">v${version}</span></a>
<nav><a href="${BASE}/docs/readme.html">Guide</a><a href="${BASE}/docs/results.html">Benchmarks</a><a href="${BASE}/docs/spec.html">Spec</a><a href="${BASE}/docs/roadmap.html">Roadmap</a><a href="https://github.com/dwarka-prasad/distillr">GitHub</a><button id="theme" aria-label="Toggle theme">◐</button></nav></header>
${docs ? `<div class="wrap"><aside class="side">${nav}</aside><main class="content" data-slug="${slug}">${body}</main></div>` : body}
<footer>Distillr · Apache-2.0 · <a href="https://github.com/dwarka-prasad/distillr">Source</a> · built by <a href="https://dwarka-prasad.github.io/">Dwarka Prasad Bairwa</a></footer>
<script src="https://cdn.jsdelivr.net/npm/lucide@0.469.0/dist/umd/lucide.min.js"></script>
<script type="module">
import { animate, inView, stagger } from "https://cdn.jsdelivr.net/npm/motion@11.15.0/+esm";
window.lucide?.createIcons();
document.getElementById("theme").onclick = () => { const n = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"; document.documentElement.setAttribute("data-theme", n); localStorage.setItem("distillr_theme", n); };
const s = document.querySelector("main[data-slug]")?.dataset.slug; if (s) document.querySelector('.side a[data-slug="'+s+'"]')?.classList.add("on");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
for (const el of document.querySelectorAll("[data-reveal]")) { if (reduce) { el.classList.add("in"); continue; } inView(el, () => el.classList.add("in"), { margin: "0px 0px -10% 0px" }); }
if (document.body.classList.contains("landing") && !reduce) animate(".hero [data-reveal]", { opacity: [0, 1], y: [16, 0] }, { delay: stagger(0.08, { startDelay: 0.05 }), duration: 0.7, easing: [0.22, 1, 0.36, 1] });
for (const el of document.querySelectorAll("[data-count]")) {
  const target = Number(el.dataset.count), dec = Number(el.dataset.decimals ?? 0), pre = el.dataset.prefix ?? "", suf = el.dataset.suffix ?? "";
  const fmt = (v) => pre + (dec ? v.toFixed(dec) : Math.round(v).toLocaleString()) + suf;
  if (reduce) { el.textContent = fmt(target); continue; }
  inView(el, () => animate(0, target, { duration: 1.4, easing: [0.22, 1, 0.36, 1], onUpdate: (v) => { el.textContent = fmt(v); } }), { amount: 0.5 });
}
// token bars animate to width
for (const b of document.querySelectorAll(".bar span")) { const w = b.dataset.w; b.style.width = "0%"; inView(b, () => animate(b, { width: [ "0%", w + "%" ] }, { duration: 1, easing: [0.22, 1, 0.36, 1] }), { amount: 0.5 }); }
for (const b of document.querySelectorAll(".tabs button")) b.onclick = () => { document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b)); document.querySelectorAll(".tabpanes pre").forEach((p) => p.classList.toggle("on", p.dataset.pane === b.dataset.tab)); };
// ---- pipeline flow diagram ----
const flow = document.querySelector(".flow");
if (flow) {
  const nodes = [...flow.querySelectorAll(".node")];
  const conns = [...flow.querySelectorAll(".conn")];
  const maxTok = Math.max(...nodes.map((n) => Number(n.dataset.tokens || 0)));
  const fmt = (v) => Math.round(v).toLocaleString();
  const widthFor = (tok) => Math.max(6, Math.sqrt(tok / maxTok) * 108);
  const setBar = (n, tok) => { const bar = n.querySelector(".bar"); if (bar) bar.setAttribute("width", widthFor(tok)); };
  const setNum = (n, v) => { const t = n.querySelector(".n"); if (t) t.textContent = fmt(v); };
  const play = () => {
    flow.classList.remove("play");
    nodes.forEach((n) => { n.querySelector(".inner").style.opacity = 0; n.classList.remove("lit"); const bar = n.querySelector(".bar"); if (bar) bar.setAttribute("width", 0); setNum(n, 0); });
    conns.forEach((c) => { c.style.strokeDashoffset = 60; });
    if (reduce) {
      nodes.forEach((n) => { n.querySelector(".inner").style.opacity = 1; n.classList.add("lit"); const tok = Number(n.dataset.tokens || 0); if (tok) { setBar(n, tok); setNum(n, tok); } });
      conns.forEach((c) => { c.style.strokeDashoffset = 0; });
      flow.classList.add("play");
      return;
    }
    let prev = maxTok;
    nodes.forEach((n, i) => {
      const tok = Number(n.dataset.tokens || 0);
      const inner = n.querySelector(".inner"), bar = n.querySelector(".bar");
      const at = i * 0.55;
      animate(inner, { opacity: [0, 1], y: [10, 0] }, { duration: 0.5, delay: at, easing: [0.22, 1, 0.36, 1] }).finished.then(() => n.classList.add("lit"));
      if (conns[i - 1]) animate(conns[i - 1], { strokeDashoffset: [60, 0] }, { duration: 0.45, delay: Math.max(0, at - 0.25), easing: "ease-out" });
      if (bar && tok) {
        const from = i === 0 ? 0 : widthFor(prev), to = widthFor(tok), start = i === 0 ? 0 : prev;
        animate((p) => { bar.setAttribute("width", from + (to - from) * p); setNum(n, start + (tok - start) * p); }, { duration: 0.8, delay: at + 0.15, easing: [0.22, 1, 0.36, 1] });
        prev = tok;
      }
    });
    setTimeout(() => flow.classList.add("play"), nodes.length * 550);
  };
  // Show the finished state first (no-JS / slow-network safe), then animate on first view.
  nodes.forEach((n) => { const tok = Number(n.dataset.tokens || 0); if (tok) { setBar(n, tok); setNum(n, tok); } n.classList.add("lit"); });
  flow.classList.add("play");
  let played = false;
  inView(flow, () => { if (!played) { played = true; play(); } }, { amount: 0.4 });
  document.getElementById("replay")?.addEventListener("click", play);
}
// ---- cross-page transitions (fallback for browsers without cross-document view transitions) ----
if (!("startViewTransition" in document) && !reduce) {
  document.body.classList.add("arrive");
  for (const a of document.querySelectorAll('a[href^="/distillr/"]')) a.addEventListener("click", (e) => { if (e.metaKey || e.ctrlKey || a.target === "_blank") return; e.preventDefault(); document.body.classList.add("leaving"); setTimeout(() => { location.href = a.href; }, 180); });
}
fetch("https://api.github.com/repos/dwarka-prasad/distillr").then((r) => r.ok ? r.json() : null).then((d) => { const el = document.getElementById("stars"); if (d && el) el.textContent = d.stargazers_count; }).catch(() => {});
</script></body></html>`;

for (const p of pages) {
  let md = readFileSync(path.join(root, p.file), "utf8");
  md = md.replace(/\]\(benchmarks\/RESULTS\.md\)/g, `](${BASE}/docs/results.html)`).replace(/\]\(docs\/(spec|design)\.md\)/g, `](${BASE}/docs/$1.html)`)
    .replace(/\]\((CONTRIBUTING|CHANGELOG|ROADMAP|README)\.md\)/g, (_, n) => `](${BASE}/docs/${n.toLowerCase()}.html)`).replace(/\]\(docs\/\)/g, `](${BASE}/docs/spec.html)`);
  writeFileSync(path.join(out, "docs", `${p.slug}.html`), shell(p.title, marked.parse(md), { slug: p.slug }));
}
writeFileSync(path.join(out, "docs", "index.html"), `<!doctype html><meta http-equiv="refresh" content="0; url=${BASE}/docs/readme.html">`);
writeFileSync(path.join(out, "index.html"), shell("Cut LLM token spend without dropping what the model needed", readFileSync(path.join(root, "site", "landing.html"), "utf8").replaceAll("{{VERSION}}", version), { docs: false }));
writeFileSync(path.join(out, ".nojekyll"), "");
console.log(`built landing + ${pages.length} pages (v${version})`);
