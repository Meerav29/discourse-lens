<script lang="ts">
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';
	import type { ChatSource } from '#lib/api.ts';
	import { linkCitations } from '#lib/citations.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';
	import ExternalLink from '@lucide/svelte/icons/external-link';

	let {
		text,
		sources,
		streaming = false
	}: { text: string; sources: ChatSource[]; streaming?: boolean } = $props();

	const ws = $derived(useWorkspace());

	// While streaming, a caret goes into the markdown itself so it lands right
	// after the last word, even inside a list item.
	const CARET = '<span class="caret" aria-hidden="true"></span>';

	// LLM output can echo text from scraped pages: never trust it as HTML.
	// Citation buttons and the caret are added before sanitising, so DOMPurify vets them too.
	const html = $derived(
		DOMPurify.sanitize(
			marked.parse(linkCitations(text, sources) + (streaming ? CARET : ''), {
				async: false,
				gfm: true,
				breaks: true
			})
		)
	);

	// Until the answer is done, every retrieved source might still be cited.
	const cited = $derived(sources.filter((s) => s.cited ?? true));
	const uncited = $derived(sources.filter((s) => s.cited === false));

	function open(s: ChatSource) {
		ws.openArticleById(s.article_id);
	}

	function onclick(e: MouseEvent) {
		const button = (e.target as HTMLElement).closest<HTMLElement>('[data-cite]');
		if (!button) return;
		const s = sources.find((x) => x.n === Number(button.dataset.cite));
		if (s) open(s);
	}
</script>

{#snippet sourceRow(s: ChatSource)}
	<li class="flex items-baseline gap-2">
		<span class="w-5 shrink-0 text-right text-muted tabular">{s.n}</span>
		{#if ws.articles.some((a) => a.id === s.article_id)}
			<button
				type="button"
				class="min-w-0 truncate text-left text-ink-2 hover:text-ink hover:underline"
				onclick={() => open(s)}
			>
				{s.title}
			</button>
		{:else}
			<!-- eslint-disable svelte/no-navigation-without-resolve -- external source URL -->
			<a
				href={s.url}
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex min-w-0 items-center gap-1 truncate text-ink-2 hover:text-ink hover:underline"
			>
				{s.title}
				<ExternalLink size={12} aria-hidden="true" />
			</a>
			<!-- eslint-enable svelte/no-navigation-without-resolve -->
		{/if}
		<span class="ml-auto shrink-0 text-muted">{s.domain}</span>
	</li>
{/snippet}

<article>
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<!-- (delegation only: the citation targets inside are real <button>s) -->
	<div class="answer prose prose-sm max-w-none" {onclick}>
		<!-- eslint-disable-next-line svelte/no-at-html-tags -- sanitized by DOMPurify above -->
		{@html html}
	</div>

	{#if cited.length}
		<h3 class="mt-5 text-sm font-semibold">Sources</h3>
		<ol class="mt-2 space-y-1 text-sm">
			{#each cited as s (s.n)}{@render sourceRow(s)}{/each}
		</ol>
	{/if}
	{#if uncited.length}
		<details class="mt-2 text-sm">
			<summary class="cursor-pointer text-muted hover:text-ink">
				Also searched, not cited ({uncited.length})
			</summary>
			<ol class="mt-2 space-y-1">
				{#each uncited as s (s.n)}{@render sourceRow(s)}{/each}
			</ol>
		</details>
	{/if}
</article>

<style>
	.answer {
		--tw-prose-body: var(--ink-2);
		--tw-prose-headings: var(--ink);
		--tw-prose-bold: var(--ink);
		--tw-prose-links: var(--ink);
		--tw-prose-bullets: var(--muted);
		--tw-prose-counters: var(--muted);
		--tw-prose-quotes: var(--ink-2);
		--tw-prose-quote-borders: var(--rule);
		--tw-prose-hr: var(--rule);
		--tw-prose-code: var(--ink);
		font-size: 0.98rem;
	}
	.answer :global(a) {
		overflow-wrap: anywhere;
	}
	.answer :global(.cite) {
		display: inline-grid;
		place-items: center;
		min-width: 1.15rem;
		height: 1.15rem;
		margin: 0 1px;
		padding: 0 3px;
		border-radius: 4px;
		background: var(--rule-soft);
		color: var(--ink);
		font-size: 0.72rem;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		vertical-align: 0.15em;
		line-height: 1;
		cursor: pointer;
	}
	.answer :global(.cite:hover) {
		background: var(--accent);
		color: var(--accent-ink);
	}
	/* a caret while the answer is being written */
	.answer :global(.caret) {
		display: inline-block;
		width: 0.45em;
		height: 1em;
		margin-left: 2px;
		vertical-align: -0.12em;
		background: var(--accent);
		animation: blink 1s steps(1) infinite;
	}
	@keyframes blink {
		50% {
			opacity: 0;
		}
	}
</style>
