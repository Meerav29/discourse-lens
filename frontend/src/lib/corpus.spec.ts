import { describe, expect, it } from 'vitest';
import type { CorpusPoint } from '#lib/api.ts';
import {
	aggregateArticles,
	buildTimeline,
	distinctiveTerms,
	MAX_HUES,
	parseYearMonth,
	summarizeClusters,
	tokenize,
	type ArticlePoint
} from './corpus';

function point(over: Partial<CorpusPoint>): CorpusPoint {
	return {
		chunk_id: 'c',
		article_id: 'a',
		child_text: '',
		url: 'https://x.test/a',
		title: 'A',
		domain: 'x.test',
		publish_date: null,
		x: 0,
		y: 0,
		cluster_id: 0,
		cluster_label: 'Zero',
		distance_from_centroid: 0,
		word_count: 500,
		...over
	};
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
		chunks: 1,
		distance: 0,
		...over
	};
}

describe('aggregateArticles', () => {
	it('uses the majority cluster and averages only its chunks', () => {
		const [a] = aggregateArticles([
			point({
				chunk_id: '1',
				cluster_id: 1,
				cluster_label: 'One',
				x: 2,
				y: 2,
				distance_from_centroid: 0.4
			}),
			point({
				chunk_id: '2',
				cluster_id: 1,
				cluster_label: 'One',
				x: 4,
				y: 6,
				distance_from_centroid: 0.7
			}),
			point({ chunk_id: '3', cluster_id: 0, x: 100, y: 100, distance_from_centroid: 9 })
		]);
		expect(a.clusterId).toBe(1);
		expect(a.clusterLabel).toBe('One');
		expect([a.x, a.y]).toEqual([3, 4]);
		expect(a.chunks).toBe(3);
		// outlier score only counts chunks in the article's own cluster
		expect(a.distance).toBe(0.7);
	});

	it('breaks ties toward the lower cluster id', () => {
		const [a] = aggregateArticles([
			point({ chunk_id: '1', cluster_id: 2 }),
			point({ chunk_id: '2', cluster_id: 1 })
		]);
		expect(a.clusterId).toBe(1);
	});
});

describe('summarizeClusters', () => {
	it('gives hues to the largest clusters and folds the rest', () => {
		const articles: ArticlePoint[] = [];
		for (let c = 0; c < MAX_HUES + 2; c++) {
			for (let i = 0; i <= c; i++) articles.push(article({ id: `${c}-${i}`, clusterId: c }));
		}
		const clusters = summarizeClusters(articles);
		expect(clusters[0]).toMatchObject({ id: MAX_HUES + 1, slot: 1 });
		expect(clusters.filter((c) => c.slot === null).map((c) => c.id)).toEqual([1, 0]);
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

describe('distinctiveTerms', () => {
	it('ranks words specific to a cluster above shared ones', () => {
		const pts: CorpusPoint[] = [];
		for (let i = 0; i < 4; i++) {
			pts.push(point({ cluster_id: 0, child_text: 'rebound effect energy demand' }));
			pts.push(point({ cluster_id: 1, child_text: 'carbon pricing energy policy' }));
		}
		const terms = distinctiveTerms(pts);
		const zero = terms.get(0)!.map((t) => t.term);
		expect(zero).toContain('rebound');
		expect(zero).not.toContain('energy'); // in every chunk → idf 0
		expect(terms.get(0)![0].share).toBe(1);
	});
});

describe('tokenize', () => {
	it('ignores URLs', () => {
		expect(tokenize('see https://example.com/heat-study and www.city.gov/plan today')).toEqual([
			'today'
		]);
	});

	it('drops stop words, short words, numbers and possessives', () => {
		expect(tokenize("Jevons's paradox: efficiency would raise 2024 demand")).toEqual([
			'jevons',
			'paradox',
			'efficiency',
			'raise',
			'demand'
		]);
	});
});
