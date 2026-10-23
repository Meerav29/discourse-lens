// Headless checks for the prototype (design.md section 8, P1-P7) plus screenshots.
//
//   python make_test_contracts.py && for f in variant no-xy synthetic-150; do
//     python build_map.py test-contracts/$f.json out/$f.html; done
//   NODE_PATH=$(npm root -g) node check.cjs        # needs the `playwright` package + Chromium
//
// Writes check-results.json and screenshots/*.png next to this file.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { chromium } = require("playwright");

const HERE = __dirname;
const SHOTS = path.join(HERE, "screenshots");
const FIXTURE = JSON.parse(fs.readFileSync(path.join(HERE, "../fixtures/reference-map-jevons.json"), "utf8"));
const url = f => "file://" + path.join(HERE, f);
fs.mkdirSync(SHOTS, { recursive: true });

async function open(browser, file, width, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: opts.height || 900 }, hasTouch: !!opts.touch,
    isMobile: !!opts.touch, deviceScaleFactor: opts.dpr || 1, colorScheme: opts.scheme || "light" });
  const page = await ctx.newPage();
  const errors = [], requests = [];
  page.on("console", m => { if (m.type() === "error" || m.type() === "warning") errors.push(m.type() + ": " + m.text()); });
  page.on("pageerror", e => errors.push("pageerror: " + e.message));
  page.on("request", r => { if (!r.url().startsWith("file://")) requests.push(r.url()); });
  await page.goto(url(file) + (opts.hash || ""));
  await page.waitForTimeout(300);
  return { ctx, page, errors, requests };
}
const hashNodes = nodes => crypto.createHash("sha256").update(nodes.map(n => n.id + ":" + n.x.toFixed(2) + "," + n.y.toFixed(2)).join(";")).digest("hex").slice(0, 16);
const overlaps = labels => { const o = []; for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
  const a = labels[i].box, b = labels[j].box; if (a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1) o.push([labels[i].i, labels[j].i]); } return o; };
function centroids(points, key) { const m = new Map(); points.forEach(p => { const k = key(p); if (k == null) return;
  const c = m.get(k) || { x: 0, y: 0, n: 0 }; c.x += p.x; c.y += p.y; c.n++; m.set(k, c); });
  m.forEach(c => { c.x /= c.n; c.y /= c.n; }); return m; }
function nearestTopic(cents) { const out = {}; cents.forEach((c, k) => { let best = null, bd = Infinity;
  cents.forEach((d, j) => { if (j === k) return; const dd = Math.hypot(c.x - d.x, c.y - d.y); if (dd < bd) { bd = dd; best = j; } }); out[k] = best; }); return out; }

(async () => {
  const browser = await chromium.launch();
  const R = { generated_at: new Date().toISOString(), chromium: browser.version(), pages: {} };
  const map1440 = await open(browser, "map.html", 1440);
  const map390 = await open(browser, "map.html", 390, { height: 844, touch: true });
  const dl = await map1440.page.evaluate(() => window.__dl);
  const dl390 = await map390.page.evaluate(() => window.__dl);
  const U = FIXTURE.clusters.length;

  // P1
  const size = fs.statSync(path.join(HERE, "map.html")).size;
  R.P1 = { bytes: size, under_1mb: size < 1048576, requests_1440: map1440.requests, requests_390: map390.requests };

  // P2
  const again = await open(browser, "map.html", 1440);
  const dlAgain = await again.page.evaluate(() => window.__dl);
  const noxy = await open(browser, "out/no-xy.html", 1440);
  const dlNoxy = await noxy.page.evaluate(() => window.__dl);
  const syn = await open(browser, "out/synthetic-150.html", 1440);
  const dlSyn = await syn.page.evaluate(() => window.__dl);
  R.P2 = { hash_load1: hashNodes(dl.nodes), hash_load2: hashNodes(dlAgain.nodes), hash_without_xy: hashNodes(dlNoxy.nodes),
    hash_390: hashNodes(dl390.nodes), layout_ms_fixture52: +dl.ms.toFixed(1), layout_ms_synthetic150: +dlSyn.ms.toFixed(1),
    synthetic_errors: syn.errors };

  // P3
  const own = centroids(dl.nodes, n => (n.i < U ? n.i : null));
  let closer = 0, total = 0;
  dl.nodes.forEach(n => { if (n.i >= U) return; total++; const d0 = Math.hypot(n.x - own.get(n.i).x, n.y - own.get(n.i).y);
    let ok = true; own.forEach((c, k) => { if (k !== n.i && Math.hypot(n.x - c.x, n.y - c.y) < d0) ok = false; }); if (ok) closer++; });
  R.P3 = { closer_to_own_centroid: closer, clustered: total, pct: +(100 * closer / total).toFixed(1),
    label_overlaps_1440: overlaps(dl.labels), label_overlaps_390: overlaps(dl390.labels), labels_1440: dl.labels.length, labels_390: dl390.labels.length };

  // P4
  const umap = centroids(FIXTURE.articles, a => (a.cluster_id >= 0 ? a.cluster_id : null));
  const umapIdx = new Map([...umap].map(([cid, c]) => [FIXTURE.clusters.findIndex(k => k.cluster_id === cid), c]));
  const nU = nearestTopic(umapIdx), nL = nearestTopic(own);
  R.P4 = { rows: FIXTURE.clusters.map((c, i) => ({ topic: c.label, nearest_in_app_umap: FIXTURE.clusters[nU[i]].label,
    nearest_in_computed: FIXTURE.clusters[nL[i]].label, match: nU[i] === nL[i] })) };
  R.P4.matches = R.P4.rows.filter(r => r.match).length;

  // P5: claims view
  const p = map1440.page;
  await p.click('nav [data-v="claims"]');
  const claims = await p.evaluate(() => {
    const ds = [...document.querySelectorAll("#v-claims details.prop")];
    const counts = ds.map(d => Object.fromEntries([...d.querySelectorAll(".counts [data-k]")].map(s => [s.dataset.k, parseInt(s.textContent)])));
    return { n: ds.length, order: ds.map(d => +d.dataset.position), counts };
  });
  const expectedOrder = FIXTURE.propositions.map(pr => { const n = { agrees: 0, qualifies: 0, disputes: 0 }; pr.stances.forEach(s => n[s.stance]++);
    return { pos: pr.position, qd: n.qualifies + n.disputes, tot: pr.stances.length }; })
    .sort((a, b) => b.qd - a.qd || b.tot - a.tot || a.pos - b.pos).map(x => x.pos);
  const sum = claims.counts.reduce((s, c) => s + c.agrees + c.qualifies + c.disputes, 0);
  await p.click("#v-claims details.prop >> nth=0");
  const exp = await p.evaluate(() => [...document.querySelectorAll("#v-claims details.prop")[0].querySelectorAll(".stance a")].map(a => a.href));
  const urls = new Set(FIXTURE.articles.map(a => a.url));
  const firstProp = FIXTURE.propositions.find(pr => pr.position === claims.order[0]);
  R.P5 = { propositions_shown: claims.n, stance_total: sum, order_shown: claims.order, order_expected: expectedOrder,
    order_ok: JSON.stringify(claims.order) === JSON.stringify(expectedOrder), expanded_links: exp.length,
    expanded_links_expected: firstProp.stances.length, links_all_known_urls: exp.every(h => urls.has(h) || urls.has(decodeURI(h))) };
  await p.screenshot({ path: path.join(SHOTS, "claims-1440.png"), fullPage: true });

  // P6: hover (desktop), tap (390), topic filter, null-title fallback
  await p.click('nav [data-v="map"]');
  await p.waitForTimeout(100);
  const svgBox = await p.locator("#map").boundingBox();
  const scr = await p.evaluate(() => window.__dl.screen);
  const target = scr.find(s => s.id === FIXTURE.articles[0].id);
  await p.mouse.move(svgBox.x + target.x, svgBox.y + target.y);
  await p.waitForTimeout(80);
  const tip = await p.evaluate(() => ({ shown: getComputedStyle(document.getElementById("tip")).display !== "none", text: document.getElementById("tip").innerText }));
  await p.screenshot({ path: path.join(SHOTS, "map-1440-hover.png") });
  const nullArt = FIXTURE.articles.find(a => !a.title);
  const nt = scr.find(s => s.id === nullArt.id);
  await p.mouse.click(svgBox.x + nt.x, svgBox.y + nt.y);
  await p.waitForTimeout(80);
  const nullCard = await p.evaluate(() => document.querySelector("#card.on h2")?.textContent);
  await p.keyboard.press("Escape");
  // topic filter: click the topic button for cluster index 1
  await p.click("#topics .topic >> nth=1");
  const filt = await p.evaluate(() => ({ dimmed: document.querySelectorAll("#map circle.dim").length,
    claims: document.querySelectorAll("#v-claims details.prop").length, rows: document.querySelectorAll("#tbl tbody tr").length }));
  await p.screenshot({ path: path.join(SHOTS, "map-1440-topic-selected.png") });
  await p.click("#fclear");
  // 390 tap
  const q = map390.page;
  const box390 = await q.locator("#map").boundingBox();
  const t390 = dl390.screen.find(s => s.id === FIXTURE.articles[5].id);
  await q.touchscreen.tap(box390.x + t390.x, box390.y + t390.y);
  await q.waitForTimeout(100);
  const tap = await q.evaluate(() => ({ cardShown: document.getElementById("card").classList.contains("on"),
    card_title: document.querySelector("#card h2")?.textContent, card_sub: document.querySelector("#card .sub")?.textContent }));
  await q.screenshot({ path: path.join(SHOTS, "map-390-tap.png") });
  R.P6 = { hover_tooltip_shown: tip.shown, hover_text: tip.text, tap_390: tap, null_title_card: nullCard, null_title_domain: nullArt.domain,
    topic_filter: { topic: FIXTURE.clusters[1].label, topic_size: FIXTURE.clusters[1].article_count, ...filt } };

  // Clean screenshots of every tab at both widths
  await q.keyboard.press("Escape");
  const clean1440 = await open(browser, "map.html", 1440);
  await clean1440.page.screenshot({ path: path.join(SHOTS, "map-1440.png"), fullPage: true });
  await clean1440.page.click('nav [data-v="sources"]');
  await clean1440.page.screenshot({ path: path.join(SHOTS, "sources-1440.png") });
  const clean390 = await open(browser, "map.html", 390, { height: 844, touch: true });
  await clean390.page.screenshot({ path: path.join(SHOTS, "map-390.png"), fullPage: true });
  await clean390.page.tap('nav [data-v="claims"]');
  await clean390.page.tap("#v-claims details.prop >> nth=0");
  await clean390.page.screenshot({ path: path.join(SHOTS, "claims-390.png"), fullPage: true });
  const dark = await open(browser, "map.html", 1440, { scheme: "dark" });
  await dark.page.screenshot({ path: path.join(SHOTS, "map-1440-dark.png") });

  // P7: variant contract
  const v = await open(browser, "out/variant.html", 1440);
  const vstate = await v.page.evaluate(() => ({ timelineHidden: document.getElementById("timeline").hidden,
    edgeCount: 0, meta: document.getElementById("meta").textContent }));
  await v.page.screenshot({ path: path.join(SHOTS, "variant-1440.png"), fullPage: true });
  await v.page.click('nav [data-v="claims"]');
  vstate.claimsText = await v.page.evaluate(() => document.getElementById("v-claims").innerText);
  const v390 = await open(browser, "out/variant.html", 390, { height: 844, touch: true });
  const fxTimeline = await map1440.page.evaluate(() => !document.getElementById("timeline").hidden);
  R.P7 = { ...vstate, fixture_timeline_shown: fxTimeline, errors_1440: v.errors, errors_390: v390.errors };

  // Side-by-side: fixture UMAP x/y vs the computed layout, same colours
  const colors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
  const panel = (pts, title) => { const xs = pts.map(p => p.x), ys = pts.map(p => p.y), x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const s = Math.min(440 / (x1 - x0), 440 / (y1 - y0)), X = x => 90 + (x - x0) * s, Y = y => 70 + (y - y0) * s;
    const cents = centroids(pts, p => (p.i < U ? p.i : null));
    return `<svg width="620" height="560"><text x="20" y="28" font-size="16" font-weight="600">${title}</text>` +
      pts.map(p => `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="5" fill="${p.i < U ? colors[p.i] : "#a3a29a"}" stroke="#fff"/>`).join("") +
      [...cents].map(([i, c]) => `<text x="${X(c.x)}" y="${Y(c.y)}" font-size="12" font-weight="600" text-anchor="middle" stroke="#fff" stroke-width="3" paint-order="stroke">${FIXTURE.clusters[i].label}</text>`).join("") + "</svg>"; };
  const fxPts = FIXTURE.articles.map(a => ({ x: a.x, y: -a.y, i: a.cluster_id >= 0 ? FIXTURE.clusters.findIndex(c => c.cluster_id === a.cluster_id) : U }));
  const html = `<!doctype html><meta charset="utf-8"><body style="margin:0;font-family:system-ui;background:#fcfcfb;display:flex;gap:10px">` +
    panel(fxPts, "App: UMAP of embeddings (fixture x/y)") + panel(dl.nodes, "Prototype: computed in the browser (x/y ignored)") + "</body>";
  fs.writeFileSync(path.join(HERE, "out/compare.html"), html);
  const cmp = await open(browser, "out/compare.html", 1260, { height: 560 });
  await cmp.page.screenshot({ path: path.join(SHOTS, "side-by-side.png") });

  R.console = { map_1440: map1440.errors, map_390: map390.errors, clean_1440: clean1440.errors, clean_390: clean390.errors, dark: dark.errors };
  fs.writeFileSync(path.join(HERE, "check-results.json"), JSON.stringify(R, null, 1) + "\n");
  console.log(JSON.stringify(R, null, 1));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
