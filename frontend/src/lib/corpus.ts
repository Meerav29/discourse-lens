/**
 * Shaping the API's map data for the views.
 * Pure functions — no DOM, no Svelte — so they're unit-tested directly.
 */
import type { Cluster, MapArticle, Term } from '#lib/api.ts';

/** Articles the topic model couldn't place in any topic. */
export const UNCLUSTERED = -1;

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
	/** Cosine distance to its topic's centre: the outlier score */
	distance: number;
}

export interface ClusterInfo {
	id: number;
	label: string;
	description: string | null;
	articles: number;
	terms: Term[];
	/** 1-8: a categorical hue slot; null: the neutral ink (unclustered, or past 8) */
	slot: number | null;
}

export const MAX_HUES = 8;

/**
 * Topics largest first, then "Unclustered" last if any article is. The
 * largest MAX_HUES topics take the categorical slots in fixed order (the
 * backend caps topics at 8, so normally every topic gets one).
 */
export function summarizeClusters(clusters: Cluster[], articles: MapArticle[]): ClusterInfo[] {
	const ordered: ClusterInfo[] = [...clusters]
		.sort((a, b) => b.article_count - a.article_count || a.cluster_id - b.cluster_id)
		.map((c, i) => ({
			id: c.cluster_id,
			label: c.label,
			description: c.description,
			articles: c.article_count,
			terms: c.terms,
			slot: i < MAX_HUES ? i + 1 : null
		}));
	const unclustered = articles.filter((a) => a.cluster_id === UNCLUSTERED).length;
	if (unclustered > 0) {
		ordered.push({
			id: UNCLUSTERED,
			label: 'Unclustered',
			description: "Articles that don't fit any topic well enough to join it.",
			articles: unclustered,
			terms: [],
			slot: null
		});
	}
	return ordered;
}

export function toArticlePoints(articles: MapArticle[], clusters: ClusterInfo[]): ArticlePoint[] {
	const labels = new Map(clusters.map((c) => [c.id, c.label]));
	return articles.map((a) => ({
		id: a.article_id,
		title: a.title || a.domain || 'Untitled',
		url: a.url,
		domain: a.domain ?? '',
		date: a.publish_date,
		wordCount: a.word_count ?? 0,
		clusterId: a.cluster_id,
		clusterLabel: labels.get(a.cluster_id) ?? 'Unclustered',
		x: a.x,
		y: a.y,
		distance: a.distance
	}));
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
