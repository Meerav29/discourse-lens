import type { Proposition, PropositionClaim } from '#lib/api.ts';

export type Stance = PropositionClaim['stance'];
export type Order = 'debated' | 'sources';

export const STANCES: { stance: Stance; label: string; verb: string; color: string }[] = [
	{ stance: 'agrees', label: 'Agree', verb: 'agree', color: 'var(--ink-2)' },
	{ stance: 'qualifies', label: 'Qualify', verb: 'qualify', color: 'var(--series-other)' },
	{ stance: 'disputes', label: 'Dispute', verb: 'dispute', color: 'var(--accent)' }
];

// Measured on a 52-article map: $0.27 with Claude Sonnet ($2 / $10 per million tokens).
const DOLLARS_PER_ARTICLE = 0.0055;

export function tally(p: Proposition): Record<Stance, number> {
	const counts: Record<Stance, number> = { agrees: 0, qualifies: 0, disputes: 0 };
	for (const c of p.claims) counts[c.stance] += 1;
	return counts;
}

/** 0 when every article agrees; higher the more of them qualify or dispute. */
export function disagreement(p: Proposition): number {
	const t = tally(p);
	return (t.disputes + t.qualifies / 2) / p.claims.length;
}

/** Most debated first, or most articles first; ties keep the order Claude gave. */
export function ordered(props: Proposition[], order: Order): Proposition[] {
	const key =
		order === 'debated'
			? (p: Proposition) => [disagreement(p), p.claims.length]
			: (p: Proposition) => [p.claims.length, disagreement(p)];
	return props
		.map((p, i) => ({ p, i, k: key(p) }))
		.toSorted((a, b) => b.k[0] - a.k[0] || b.k[1] - a.k[1] || a.i - b.i)
		.map(({ p }) => p);
}

/** "about $0.30" for a map of n articles */
export function estimate(articles: number): string {
	const dollars = Math.max(0.05, Math.ceil(articles * DOLLARS_PER_ARTICLE * 20) / 20);
	return `about $${dollars.toFixed(2)}`;
}
