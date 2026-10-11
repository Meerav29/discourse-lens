/**
 * Turning the API's chunk-level corpus into article-level views.
 * Pure functions — no DOM, no Svelte — so they're unit-tested directly.
 */
import type { CorpusPoint } from '#lib/api.ts';

export interface ArticlePoint {
	id: string;
	title: string;
	url: string;
	domain: string;
	date: string | null; // YYYY-MM or YYYY-MM-DD
	wordCount: number;
	clusterId: number;
	clusterLabel: string;
	x: number;
	y: number;
	chunks: number;
	/** Furthest any of its chunks sits from its cluster's centre (outlier score) */
	distance: number;
}

/**
 * One point per article. Its cluster is the one most of its chunks fall in,
 * and its position is the mean of those chunks only — averaging every chunk
 * can drop an article into empty space between clusters.
 */
export function aggregateArticles(points: CorpusPoint[]): ArticlePoint[] {
	const byArticle = new Map<string, CorpusPoint[]>();
	for (const p of points) {
		const list = byArticle.get(p.article_id);
		if (list) list.push(p);
		else byArticle.set(p.article_id, [p]);
	}

	const articles: ArticlePoint[] = [];
	for (const [id, chunks] of byArticle) {
		const counts = new Map<number, number>();
		for (const c of chunks) counts.set(c.cluster_id, (counts.get(c.cluster_id) ?? 0) + 1);
		// Majority cluster; ties go to the lower cluster id for stability.
		const clusterId = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0][0];
		const inCluster = chunks.filter((c) => c.cluster_id === clusterId);
		const first = inCluster[0];
		articles.push({
			id,
			title: first.title || first.domain || 'Untitled',
			url: first.url,
			domain: first.domain ?? '',
			date: first.publish_date,
			wordCount: first.word_count ?? 0,
			clusterId,
			clusterLabel: first.cluster_label || `Cluster ${clusterId + 1}`,
			x: mean(inCluster.map((c) => c.x)),
			y: mean(inCluster.map((c) => c.y)),
			chunks: chunks.length,
			distance: Math.max(...inCluster.map((c) => c.distance_from_centroid))
		});
	}
	return articles;
}

export interface ClusterInfo {
	id: number;
	label: string;
	articles: number;
	/** 1-8: a categorical hue slot; null: folded into the neutral "other" ink */
	slot: number | null;
}

export const MAX_HUES = 8;

/**
 * Clusters ordered by size. The largest MAX_HUES take the categorical slots in
 * fixed order; any beyond that share the neutral ink — a ninth hue would not be
 * distinguishable. Labels still name every cluster on the map and in the key.
 */
export function summarizeClusters(articles: ArticlePoint[]): ClusterInfo[] {
	const map = new Map<number, ClusterInfo>();
	for (const a of articles) {
		const c = map.get(a.clusterId);
		if (c) c.articles++;
		else map.set(a.clusterId, { id: a.clusterId, label: a.clusterLabel, articles: 1, slot: null });
	}
	const ordered = [...map.values()].sort((a, b) => b.articles - a.articles || a.id - b.id);
	ordered.forEach((c, i) => (c.slot = i < MAX_HUES ? i + 1 : null));
	return ordered;
}

export function clusterColor(slot: number | null): string {
	return slot == null ? 'var(--series-other)' : `var(--series-${slot})`;
}

// ── Timeline ────────────────────────────────────────────────────────────────

export interface TimelineBin {
	key: string; // YYYY or YYYY-MM
	start: Date;
	counts: Record<number, number>;
	total: number;
}

export interface Timeline {
	unit: 'month' | 'year';
	bins: TimelineBin[];
	dated: number;
	undated: number;
}

/** Spans longer than this many months are binned by year instead. */
export const MONTHLY_SPAN_LIMIT = 36;

export function buildTimeline(articles: ArticlePoint[], clusterIds: number[]): Timeline {
	const dated = articles
		.map((a) => ({ a, ym: parseYearMonth(a.date) }))
		.filter((d): d is { a: ArticlePoint; ym: [number, number] } => d.ym !== null);
	const undated = articles.length - dated.length;
	if (dated.length === 0) return { unit: 'month', bins: [], dated: 0, undated };

	const index = (ym: [number, number]) => ym[0] * 12 + ym[1];
	const lo = Math.min(...dated.map((d) => index(d.ym)));
	const hi = Math.max(...dated.map((d) => index(d.ym)));
	const unit = hi - lo + 1 > MONTHLY_SPAN_LIMIT ? 'year' : 'month';

	const keyOf = (ym: [number, number]) =>
		unit === 'year' ? String(ym[0]) : `${ym[0]}-${String(ym[1] + 1).padStart(2, '0')}`;

	// Every bin in the range, so gaps show as zero rather than vanishing.
	const bins = new Map<string, TimelineBin>();
	const step = unit === 'year' ? 12 : 1;
	const first = unit === 'year' ? Math.floor(lo / 12) * 12 : lo;
	for (let i = first; i <= hi; i += step) {
		const ym: [number, number] = [Math.floor(i / 12), i % 12];
		const counts: Record<number, number> = {};
		for (const id of clusterIds) counts[id] = 0;
		bins.set(keyOf(ym), {
			key: keyOf(ym),
			start: new Date(Date.UTC(ym[0], unit === 'year' ? 0 : ym[1], 1)),
			counts,
			total: 0
		});
	}
	for (const { a, ym } of dated) {
		const bin = bins.get(keyOf(ym))!;
		bin.counts[a.clusterId] = (bin.counts[a.clusterId] ?? 0) + 1;
		bin.total++;
	}
	return { unit, bins: [...bins.values()], dated: dated.length, undated };
}

/** "2024-03-15" | "2024-03" → [2024, 2] (zero-based month); anything else → null */
export function parseYearMonth(date: string | null | undefined): [number, number] | null {
	const m = date?.match(/^(\d{4})-(\d{2})/);
	if (!m) return null;
	const year = Number(m[1]);
	const month = Number(m[2]) - 1;
	if (month < 0 || month > 11 || year < 1900) return null;
	return [year, month];
}

// ── Key terms ───────────────────────────────────────────────────────────────

export interface Term {
	term: string;
	score: number;
	/** score relative to the cluster's top term, 0-1 */
	share: number;
}

/**
 * Words that set each cluster apart: TF-IDF over chunks, where a term's
 * frequency inside the cluster is weighed against how many chunks across the
 * whole corpus use it. Terms in fewer than MIN_DF chunks are dropped as noise.
 */
export function distinctiveTerms(points: CorpusPoint[], perCluster = 8): Map<number, Term[]> {
	const MIN_DF = 3;
	const docs = points
		.filter((p) => p.child_text)
		.map((p) => ({ cluster: p.cluster_id, terms: tokenize(p.child_text!) }));
	const df = new Map<string, number>();
	for (const d of docs) for (const t of new Set(d.terms)) df.set(t, (df.get(t) ?? 0) + 1);

	const byCluster = new Map<number, { tf: Map<string, number>; n: number }>();
	for (const d of docs) {
		let c = byCluster.get(d.cluster);
		if (!c) byCluster.set(d.cluster, (c = { tf: new Map(), n: 0 }));
		c.n++;
		for (const t of d.terms) c.tf.set(t, (c.tf.get(t) ?? 0) + 1);
	}

	const out = new Map<number, Term[]>();
	for (const [cluster, { tf, n }] of byCluster) {
		const scored = [...tf.entries()]
			.filter(([t]) => (df.get(t) ?? 0) >= MIN_DF)
			.map(([term, count]) => ({
				term,
				score: (count / n) * Math.log(docs.length / (df.get(term) ?? 1))
			}))
			.filter((t) => t.score > 0)
			.sort((a, b) => b.score - a.score)
			.slice(0, perCluster);
		const top = scored[0]?.score || 1;
		out.set(
			cluster,
			scored.map((t) => ({ ...t, share: t.score / top }))
		);
	}
	return out;
}

export function tokenize(text: string): string[] {
	return text
		.toLowerCase()
		.replace(/\b(?:https?:\/\/|www\.)\S+/g, ' ') // URLs aren't vocabulary
		.replace(/[^a-z0-9\s'-]/g, ' ')
		.split(/\s+/)
		.map((w) => w.replace(/^['-]+|['-]+$/g, '').replace(/'s$/, ''))
		.filter((w) => w.length > 3 && !/^\d+$/.test(w) && !STOP_WORDS.has(w));
}

const STOP_WORDS = new Set(
	`about above after again against also although among another anyone anything around because been
	before being below between both cannot could does doing down during each either else even ever
	every first from further given have having here hers herself himself however into itself just
	last less like made make makes making many might more most much must myself near need neither
	never next none often once only other others ought ours ourselves over own perhaps quite rather
	really same several shall should since some something still such than that their theirs them
	themselves then there therefore these they thing things this those though through thus together
	took toward towards under until upon very want were what whatever when where whether which while
	whom whose will with within without would year years your yours yourself yourselves said says
	according also including include includes used using well across within three four five
	example however people time times way ways part help however based new however`
		.split(/\s+/)
		.filter(Boolean)
);

function mean(xs: number[]): number {
	return xs.reduce((s, x) => s + x, 0) / xs.length;
}
