import { describe, expect, it } from 'vitest';
import { linkCitations } from './citations';

const sources = [1, 2, 3, 4].map((n) => ({ n, title: `Title ${n}`, domain: 'x.test' }));
const ns = (html: string) => [...html.matchAll(/data-cite="(\d+)"/g)].map((m) => Number(m[1]));

describe('linkCitations', () => {
	it('turns single, adjacent, grouped and ranged citations into buttons', () => {
		expect(ns(linkCitations('A [2]. B [1][3]. C [1, 4]. D [2-3].', sources))).toEqual([
			2, 1, 3, 1, 4, 2, 3
		]);
	});

	it('leaves markers that name no known source alone', () => {
		const text = 'In [2024] a study [9] found it.';
		expect(linkCitations(text, sources)).toBe(text);
	});

	it('labels buttons with the source and escapes attribute text', () => {
		const html = linkCitations('[1]', [{ n: 1, title: 'A "quoted" <b>', domain: 'x.test' }]);
		expect(html).toContain('title="A &quot;quoted&quot; &lt;b> (x.test)"');
		expect(html).toContain('aria-label="Source 1:');
	});

	it('leaves markdown links untouched', () => {
		const text = 'See [the report](https://x.test) [2].';
		expect(linkCitations(text, sources)).toMatch(
			/^See \[the report\]\(https:\/\/x\.test\) <span class="cite-group"><button/
		);
	});

	it('keeps the punctuation after a citation on its line', () => {
		const html = linkCitations('Lifespan is capped [1][2]. Others disagree [3]', sources);
		expect(html).toMatch(
			/<span class="cite-group">(<button[^>]*>\d<\/button>){2}\.<\/span> Others/
		);
		expect(html).toMatch(/<button[^>]*>3<\/button><\/span>$/);
	});
});
