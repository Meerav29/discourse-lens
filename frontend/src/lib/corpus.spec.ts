import { describe, expect, it } from 'vitest';
import type { Cluster, MapArticle } from '#lib/api.ts';
import {
	buildTimeline,
	MAX_HUES,
	parseYearMonth,
	summarizeClusters,
	toArticlePoints,
	UNCLUSTERED,
	type ArticlePoint
} from './corpus';

function mapArticle(over: Partial<MapArticle>): MapArticle {
	return {
		article_id: 'a',
		url: 'https://x.test/a',
		title: 'A',
		domain: 'x.test',
		publish_date: null,
		word_count: 500,
		x: 0,
		y: 0,
		cluster_id: 0,
		distance: 0.1,
		...over
	};
}

function cluster(id: number, size: number, label = `Topic ${id}`): Cluster {
	return { cluster_id: id, label, description: null, article_count: size, terms: [] };
}

function article(over: Partial<ArticlePoint>): ArticlePoint {
	return {
		id: 'a',
		title: 'A',
		url: '',
		domain: '',
		date: null,
		wordCount: 0,
		clusterId: 0,
		clusterLabel: 'Zero',
		x: 0,
		y: 0,
		distance: 0,
		...over
	};
}

describe('summarizeClusters', () => {
	it('orders topics by size, gives each a hue, and puts unclustered last in grey', () => {
		const clusters = summarizeClusters(
			[cluster(1, 3), cluster(0, 9)],
			[mapArticle({ cluster_id: 0 }), mapArticle({ article_id: 'b', cluster_id: UNCLUSTERED })]
		);
		expect(clusters.map((c) => [c.id, c.slot])).toEqual([
			[0, 1],
			[1, 2],
			[UNCLUSTERED, null]
		]);
		expect(clusters.at(-1)).toMatchObject({ label: 'Unclustered', articles: 1 });
	});

	it('omits unclustered when every article has a topic', () => {
		expect(summarizeClusters([cluster(0, 1)], [mapArticle({})]).map((c) => c.id)).toEqual([0]);
	});

	it('folds topics past the palette into grey', () => {
		const many = Array.from({ length: MAX_HUES + 1 }, (_, i) => cluster(i, 20 - i));
		expect(summarizeClusters(many, []).at(-1)!.slot).toBeNull();
	});
});

describe('toArticlePoints', () => {
	it("maps API fields and names each article's topic", () => {
		const clusters = summarizeClusters([cluster(0, 1, 'Cool roofs')], []);
		const [a, b] = toArticlePoints(
			[
				mapArticle({ title: null, domain: 'roofs.test', x: 2, y: 3, distance: 0.4 }),
				mapArticle({ article_id: 'b', cluster_id: UNCLUSTERED })
			],
			clusters
		);
		expect(a).toMatchObject({
			id: 'a',
			title: 'roofs.test',
			clusterLabel: 'Cool roofs',
			x: 2,
			y: 3,
			distance: 0.4
		});
		expect(b.clusterLabel).toBe('Unclustered');
	});
});

describe('parseYearMonth', () => {
	it('accepts day and month precision', () => {
		expect(parseYearMonth('2024-03-15')).toEqual([2024, 2]);
		expect(parseYearMonth('2024-03')).toEqual([2024, 2]);
	});
	it('rejects missing or malformed dates', () => {
		expect(parseYearMonth(null)).toBeNull();
		expect(parseYearMonth('2024-13')).toBeNull();
		expect(parseYearMonth('March 2024')).toBeNull();
	});
});

describe('buildTimeline', () => {
	it('bins by month and fills gaps with zeros', () => {
		const t = buildTimeline(
			[
				article({ id: '1', date: '2024-01-05', clusterId: 0 }),
				article({ id: '2', date: '2024-03-01', clusterId: 1 }),
				article({ id: '3', date: null })
			],
			[0, 1]
		);
		expect(t.unit).toBe('month');
		expect(t.bins.map((b) => b.key)).toEqual(['2024-01', '2024-02', '2024-03']);
		expect(t.bins[1].total).toBe(0);
		expect(t.bins[2].counts).toEqual({ 0: 0, 1: 1 });
		expect([t.dated, t.undated]).toEqual([2, 1]);
	});

	it('switches to years for long spans', () => {
		const t = buildTimeline(
			[article({ id: '1', date: '2010-06' }), article({ id: '2', date: '2024-02' })],
			[0]
		);
		expect(t.unit).toBe('year');
		expect(t.bins[0].key).toBe('2010');
		expect(t.bins.at(-1)!.key).toBe('2024');
		expect(t.bins).toHaveLength(15);
	});

	it('handles a corpus with no dates', () => {
		expect(buildTimeline([article({})], [0])).toMatchObject({ bins: [], dated: 0, undated: 1 });
	});
});
