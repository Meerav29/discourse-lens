<script lang="ts">
	import DOMPurify from 'dompurify';
	import { marked } from 'marked';
	import { tick } from 'svelte';
	import { ask, conversation, retry } from '#lib/chat.svelte.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import ExternalLink from '@lucide/svelte/icons/external-link';

	const ws = $derived(useWorkspace());
	const chat = $derived(conversation(ws.analysis.id));

	const STARTERS = [
		'What are the main camps or schools of thought in this discourse?',
		'Where do the sources disagree most sharply?',
		'What angles look underexplored in the coverage?',
		'How has the conversation shifted over time?'
	];

	let question = $state('');
	let scroller = $state<HTMLElement>();

	// LLM output can echo text from scraped pages: never trust it as HTML.
	function render(md: string): string {
		return DOMPurify.sanitize(marked.parse(md, { async: false, gfm: true, breaks: true }));
	}

	async function send(q: string) {
		question = '';
		const done = ask(ws.analysis.id, q);
		await scrollToEnd();
		await done;
		await scrollToEnd();
	}

	async function scrollToEnd() {
		await tick();
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			if (question.trim()) send(question);
		}
	}
</script>

<div class="absolute inset-0 flex flex-col">
	<div bind:this={scroller} class="min-h-0 flex-1 overflow-y-auto">
		<div class="mx-auto max-w-3xl px-4 py-6 sm:px-6">
			{#if chat.messages.length === 0}
				<h2 class="text-xl display">Ask the corpus</h2>
				<p class="mt-2 max-w-xl text-ink-2">
					Answers come only from the {ws.articles.length} articles in this map, with the sources they
					drew on listed underneath.
				</p>
				<ul class="mt-6 grid gap-2 sm:grid-cols-2">
					{#each STARTERS as s (s)}
						<li>
							<button
								type="button"
								onclick={() => send(s)}
								class="h-full w-full rounded-md border border-rule px-4 py-3 text-left text-[0.95rem] text-ink-2 hover:border-ink-2 hover:text-ink"
							>
								{s}
							</button>
						</li>
					{/each}
				</ul>
			{/if}

			<div class="space-y-8">
				{#each chat.messages as m, i (i)}
					{#if m.role === 'user'}
						<p class="ml-auto w-fit max-w-[85%] rounded-lg bg-rule-soft px-4 py-2.5">{m.text}</p>
					{:else}
						<article>
							<!-- eslint-disable-next-line svelte/no-at-html-tags -- sanitized by DOMPurify in render() -->
							<div class="answer prose prose-sm max-w-none">{@html render(m.text)}</div>
							{#if m.citations?.length}
								<h3 class="mt-5 text-sm font-semibold">Sources</h3>
								<ol class="mt-2 space-y-1 text-sm">
									{#each m.citations as c, j (c.url)}
										{@const local = ws.articleByUrl(c.url)}
										<li class="flex items-baseline gap-2">
											<span class="w-5 shrink-0 text-right text-muted tabular">{j + 1}.</span>
											{#if local}
												<button
													type="button"
													class="min-w-0 truncate text-left text-ink-2 hover:text-ink hover:underline"
													onclick={() => ws.openArticleById(local.id)}
												>
													{c.title}
												</button>
											{:else}
												<!-- eslint-disable svelte/no-navigation-without-resolve -- external source URL -->
												<a
													href={c.url}
													target="_blank"
													rel="noopener noreferrer"
													class="inline-flex min-w-0 items-center gap-1 truncate text-ink-2 hover:text-ink hover:underline"
												>
													{c.title}
													<ExternalLink size={12} aria-hidden="true" />
												</a>
												<!-- eslint-enable svelte/no-navigation-without-resolve -->
											{/if}
											<span class="ml-auto shrink-0 text-muted">{c.domain}</span>
										</li>
									{/each}
								</ol>
							{/if}
						</article>
					{/if}
				{/each}

				{#if chat.pending}
					<p class="flex items-center gap-2 text-muted" aria-live="polite">
						<span class="size-2 animate-pulse rounded-full bg-accent"></span>
						Reading the corpus…
					</p>
				{/if}
				{#if chat.error}
					<div class="rounded-md border border-rule px-4 py-3" role="alert">
						<p class="text-danger">{chat.error}</p>
						<button
							type="button"
							class="mt-2 text-sm font-medium underline-offset-2 hover:underline"
							onclick={() => retry(ws.analysis.id)}
						>
							Ask again
						</button>
					</div>
				{/if}
			</div>
		</div>
	</div>

	<form
		class="border-t border-rule bg-paper px-4 py-3 sm:px-6"
		onsubmit={(e) => {
			e.preventDefault();
			if (question.trim()) send(question);
		}}
	>
		<div class="mx-auto flex max-w-3xl items-end gap-2">
			<label for="question" class="sr-only">Question</label>
			<textarea
				id="question"
				bind:value={question}
				onkeydown={onKey}
				rows="2"
				maxlength={2000}
				placeholder="Ask about camps, disagreements, gaps…"
				class="min-h-12 flex-1 resize-none rounded-md border border-rule bg-raised px-3 py-2.5 placeholder:text-muted focus:border-accent focus:outline-none"
			></textarea>
			<button
				type="submit"
				disabled={!question.trim() || chat.pending}
				class="grid size-12 place-items-center rounded-md bg-accent text-accent-ink hover:opacity-90 disabled:opacity-35"
				aria-label="Ask"
			>
				<ArrowUp size={18} />
			</button>
		</div>
	</form>
</div>

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
</style>
