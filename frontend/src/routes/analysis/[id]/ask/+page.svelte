<script lang="ts">
	import { tick } from 'svelte';
	import { ask, clear, conversation, loadHistory, retry, stop } from '#lib/chat.svelte.ts';
	import Answer from '#lib/components/Answer.svelte';
	import ConfirmDialog from '#lib/components/ConfirmDialog.svelte';
	import { plural } from '#lib/format.ts';
	import { useWorkspace } from '#lib/workspace.svelte.ts';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Square from '@lucide/svelte/icons/square';
	import { toast } from 'svelte-sonner';

	const ws = $derived(useWorkspace());
	const chat = $derived(conversation(ws.analysis.id));

	const STARTERS = [
		'What are the main camps, and what separates them?',
		'Where do the sources disagree most sharply?',
		'What evidence do the strongest claims rest on?',
		'What angles look underexplored in the coverage?'
	];

	let question = $state('');
	let scroller = $state<HTMLElement>();
	let input = $state<HTMLTextAreaElement>();
	let confirmClear = $state(false);

	$effect(() => {
		loadHistory(ws.analysis.id);
	});

	// Follow the answer as it streams, unless the reader has scrolled up.
	let pinned = true;
	function onScroll() {
		if (!scroller) return;
		pinned = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
	}
	$effect(() => {
		void chat.draft?.text;
		void chat.messages.length;
		if (pinned) tick().then(() => scroller?.scrollTo({ top: scroller.scrollHeight }));
	});

	function send(q: string) {
		if (!q.trim() || chat.draft) return;
		question = '';
		pinned = true;
		ask(ws.analysis.id, q);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send(question);
		}
	}

	async function clearConversation() {
		try {
			await clear(ws.analysis.id);
			input?.focus();
		} catch (e) {
			toast.error(`Couldn't clear the conversation: ${(e as Error).message}`);
		}
	}
</script>

<div class="absolute inset-0 flex flex-col">
	<div bind:this={scroller} onscroll={onScroll} class="min-h-0 flex-1 overflow-y-auto">
		<div class="mx-auto max-w-3xl px-4 py-6 sm:px-6">
			{#if chat.loadError}
				<p class="text-danger" role="alert">Couldn't load this conversation: {chat.loadError}</p>
			{:else if chat.loaded && chat.messages.length === 0 && !chat.draft}
				<h2 class="text-xl display">Ask the corpus</h2>
				<p class="mt-2 max-w-xl text-ink-2">
					Answers come only from the {plural(ws.articles.length, 'article')} in this map. Numbers like
					<span class="cite-sample">2</span> point to the article each claim rests on; click one to read
					it.
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
			{:else if chat.messages.length > 0}
				<div class="mb-6 flex justify-end">
					<button
						type="button"
						onclick={() => (confirmClear = true)}
						disabled={!!chat.draft}
						class="text-sm text-muted underline-offset-2 hover:text-ink hover:underline disabled:opacity-40"
					>
						Clear conversation
					</button>
				</div>
			{/if}

			<div class="space-y-8">
				{#each chat.messages as m, i (i)}
					{#if m.role === 'user'}
						<p class="ml-auto w-fit max-w-[85%] rounded-lg bg-rule-soft px-4 py-2.5">{m.text}</p>
					{:else}
						<Answer text={m.text} sources={m.sources ?? []} />
					{/if}
				{/each}

				{#if chat.draft}
					<p class="ml-auto w-fit max-w-[85%] rounded-lg bg-rule-soft px-4 py-2.5">
						{chat.draft.question}
					</p>
					{#if chat.draft.text}
						<Answer text={chat.draft.text} sources={chat.draft.sources} streaming />
					{:else}
						<p class="flex items-center gap-2 text-muted" aria-live="polite">
							<span class="size-2 animate-pulse rounded-full bg-accent"></span>
							{chat.draft.sources.length
								? `Reading ${plural(chat.draft.sources.length, 'article')}…`
								: 'Searching the corpus…'}
						</p>
					{/if}
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
			send(question);
		}}
	>
		<div class="mx-auto flex max-w-3xl items-end gap-2">
			<label for="question" class="sr-only">Question</label>
			<textarea
				id="question"
				bind:this={input}
				bind:value={question}
				onkeydown={onKey}
				rows="2"
				maxlength={2000}
				placeholder={chat.messages.length
					? 'Ask a follow-up…'
					: 'Ask about camps, disagreements, evidence, gaps…'}
				class="min-h-12 flex-1 resize-none rounded-md border border-rule bg-raised px-3 py-2.5 placeholder:text-muted focus:border-accent focus:outline-none"
			></textarea>
			{#if chat.draft}
				<button
					type="button"
					onclick={() => stop(ws.analysis.id)}
					class="grid size-12 place-items-center rounded-md border border-rule text-ink-2 hover:border-danger hover:text-danger"
					aria-label="Stop the answer"
					title="Stop"
				>
					<Square size={15} />
				</button>
			{:else}
				<button
					type="submit"
					disabled={!question.trim()}
					class="grid size-12 place-items-center rounded-md bg-accent text-accent-ink hover:opacity-90 disabled:opacity-35"
					aria-label="Ask"
				>
					<ArrowUp size={18} />
				</button>
			{/if}
		</div>
	</form>
</div>

<ConfirmDialog
	bind:open={confirmClear}
	title="Clear this conversation?"
	description="Every question and answer for this map will be deleted. The map itself stays."
	confirmLabel="Clear conversation"
	onconfirm={clearConversation}
/>

<style>
	.cite-sample {
		display: inline-grid;
		place-items: center;
		min-width: 1.15rem;
		height: 1.15rem;
		padding: 0 3px;
		border-radius: 4px;
		background: var(--rule-soft);
		color: var(--ink);
		font-size: 0.72rem;
		font-weight: 600;
		vertical-align: 0.15em;
	}
</style>
