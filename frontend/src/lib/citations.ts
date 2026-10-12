/**
 * Answers cite excerpts as [2], [1][3], [1, 4] or [2-4]. Before markdown
 * rendering, each valid number becomes a small button; the Ask page handles
 * clicks by delegation (data-cite) and opens that source.
 * Pure string functions so they're unit-tested without a DOM.
 */

const CITATION = /\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g;

export interface CitableSource {
	n: number;
	title: string;
	domain: string;
}

function escapeAttr(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function numbersIn(group: string): number[] {
	return group.split(/\s*,\s*/).flatMap((part) => {
		const [a, b = a] = part.split(/\s*[–-]\s*/).map(Number);
		return Array.from({ length: Math.max(0, b - a + 1) }, (_, i) => a + i);
	});
}

/** Replace citation markers with buttons; markers naming no known source stay as text. */
export function linkCitations(markdown: string, sources: CitableSource[]): string {
	const byN = new Map(sources.map((s) => [s.n, s]));
	return markdown.replace(CITATION, (match, group: string) => {
		const ns = numbersIn(group);
		if (!ns.length || !ns.every((n) => byN.has(n))) return match;
		return ns
			.map((n) => {
				const s = byN.get(n)!;
				const label = escapeAttr(`${s.title} (${s.domain})`);
				return `<button type="button" class="cite" data-cite="${n}" title="${label}" aria-label="Source ${n}: ${label}">${n}</button>`;
			})
			.join('');
	});
}
