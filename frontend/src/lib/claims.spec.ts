import { describe, expect, it } from 'vitest';
import type { Proposition } from '#lib/api.ts';
import { disagreement, estimate, ordered, tally, type Stance } from './claims.ts';

function prop(id: number, ...stances: Stance[]): Proposition {
	return {
		id,
		statement: `P${id}`,
		claims: stances.map((stance, i) => ({
			claim_id: `a${i}:0`,
			article_id: `a${i}`,
			text: 't',
			stance
		}))
	};
}

describe('claims', () => {
	it('tallies stances', () => {
		expect(tally(prop(1, 'agrees', 'disputes', 'agrees'))).toEqual({
			agrees: 2,
			qualifies: 0,
			disputes: 1
		});
	});

	it('scores disagreement, a qualification counting half', () => {
		expect(disagreement(prop(1, 'agrees', 'agrees'))).toBe(0);
		expect(disagreement(prop(1, 'agrees', 'qualifies'))).toBe(0.25);
		expect(disagreement(prop(1, 'agrees', 'disputes'))).toBe(0.5);
	});

	it('orders by debate or by sources, keeping the given order on ties', () => {
		const props = [
			prop(1, 'agrees', 'agrees', 'agrees', 'agrees'),
			prop(2, 'agrees', 'disputes'),
			prop(3, 'agrees', 'agrees'),
			prop(4, 'agrees', 'agrees')
		];
		expect(ordered(props, 'debated').map((p) => p.id)).toEqual([2, 1, 3, 4]);
		expect(ordered(props, 'sources').map((p) => p.id)).toEqual([1, 2, 3, 4]);
	});

	it('estimates cost in five-cent steps', () => {
		expect(estimate(52)).toBe('about $0.30');
		expect(estimate(3)).toBe('about $0.05');
	});
});
