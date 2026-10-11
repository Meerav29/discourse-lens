<script lang="ts">
	import { goto, invalidate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api, isRunning, type Analysis } from '#lib/api.ts';
	import ConfirmDialog from '#lib/components/ConfirmDialog.svelte';
	import StatusLabel from '#lib/components/StatusLabel.svelte';
	import ThemeToggle from '#lib/components/ThemeToggle.svelte';
	import favicon from '#lib/assets/favicon.svg';
	import { formatTimestamp } from '#lib/format.ts';
	import Trash from '@lucide/svelte/icons/trash-2';
	import { toast } from 'svelte-sonner';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const SUGGESTIONS = [
		'mechanistic interpretability in large language models',
		'longevity science and aging reversal',
		'urban heat islands and city design',
		'jevons paradox and energy efficiency'
	];

	let topic = $state('');
	let submitting = $state(false);
	let formError = $state<string | null>(null);
	let input: HTMLInputElement;

	async function start(e?: SubmitEvent) {
		e?.preventDefault();
		const t = topic.trim();
		if (!t || submitting) return;
		submitting = true;
		formError = null;
		try {
			const analysis = await api.createAnalysis(t);
			await goto(resolve('/analysis/[id]', { id: analysis.id }));
		} catch (err) {
			formError = (err as Error).message;
			submitting = false;
		}
	}

	function suggest(s: string) {
		topic = s;
		input.focus();
	}

	// Keep progress figures on running rows fresh.
	$effect(() => {
		if (!data.analyses.some(isRunning)) return;
		const timer = setInterval(() => invalidate('app:analyses'), 3000);
		return () => clearInterval(timer);
	});

	let pendingDelete = $state<Analysis | null>(null);
	let confirmOpen = $state(false);

	function askDelete(a: Analysis) {
		pendingDelete = a;
		confirmOpen = true;
	}

	async function confirmDelete() {
		const a = pendingDelete;
		if (!a) return;
		try {
			await api.deleteAnalysis(a.id);
			toast.success(`Deleted “${a.topic}”`);
			await invalidate('app:analyses');
		} catch (err) {
			toast.error(`Couldn't delete “${a.topic}”: ${(err as Error).message}`);
		}
	}
</script>

<div class="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 sm:px-8">
	<header class="flex items-center justify-between py-5">
		<a href={resolve('/')} class="flex items-center gap-2.5 text-ink">
			<img src={favicon} alt="" class="size-7" />
			<span class="text-[1.05rem] display">Discourse Lens</span>
		</a>
		<ThemeToggle />
	</header>

	<main class="flex-1 pb-20">
		<section class="max-w-3xl pt-14 pb-16 sm:pt-24">
			<h1 class="text-[2.6rem] leading-[1.05] display sm:text-[3.6rem]">Map a conversation.</h1>
			<p class="mt-5 max-w-[34rem] text-[1.075rem] text-ink-2">
				Enter a topic. Discourse Lens reads around a hundred articles about it and charts the camps,
				the outliers and how the conversation has moved. A map takes 3 to 8 minutes.
			</p>

			<form class="mt-9 flex flex-col gap-3 sm:flex-row" onsubmit={start}>
				<label class="sr-only" for="topic">Topic</label>
				<input
					id="topic"
					bind:this={input}
					bind:value={topic}
					maxlength={500}
					autocomplete="off"
					placeholder="e.g. the four-day work week"
					class="h-12 flex-1 rounded-md border border-rule bg-raised px-4 text-[1.05rem] placeholder:text-muted focus:border-accent focus:outline-none"
				/>
				<button
					type="submit"
					disabled={!topic.trim() || submitting}
					class="h-12 rounded-md bg-accent px-6 font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
				>
					{submitting ? 'Starting…' : 'Map this topic'}
				</button>
			</form>
			{#if formError}
				<p class="mt-3 text-sm text-danger" role="alert">{formError}</p>
			{/if}

			<div class="mt-5 flex flex-wrap items-baseline gap-x-1 gap-y-2 text-sm">
				<span class="mr-1 text-muted">Try</span>
				{#each SUGGESTIONS as s (s)}
					<button
						type="button"
						onclick={() => suggest(s)}
						class="rounded-full border border-rule px-3 py-1 text-ink-2 hover:border-ink-2 hover:text-ink"
					>
						{s}
					</button>
				{/each}
			</div>
		</section>

		<section aria-labelledby="maps-heading">
			<h2 id="maps-heading" class="border-b border-rule pb-3 text-lg font-semibold">Your maps</h2>
			{#if data.analyses.length === 0}
				<p class="py-10 text-ink-2">
					No maps yet. The first one shows up here as soon as it starts.
				</p>
			{:else}
				<ul>
					{#each data.analyses as a (a.id)}
						<li
							class="grid grid-cols-[1fr_auto] items-center gap-x-6 gap-y-1 border-b border-rule-soft py-4 sm:grid-cols-[1fr_11rem_8rem_2.25rem]"
						>
							<a
								href={resolve('/analysis/[id]', { id: a.id })}
								class="col-span-2 truncate font-medium text-ink hover:underline sm:col-span-1"
							>
								{a.topic}
							</a>
							<StatusLabel analysis={a} />
							<span class="hidden text-sm text-muted tabular sm:inline"
								>{formatTimestamp(a.created_ts)}</span
							>
							<button
								type="button"
								onclick={() => askDelete(a)}
								disabled={isRunning(a)}
								class="grid size-9 place-items-center rounded-md text-muted hover:bg-rule-soft hover:text-danger disabled:invisible"
								aria-label="Delete map of {a.topic}"
								title="Delete"
							>
								<Trash size={16} />
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	</main>
</div>

<ConfirmDialog
	bind:open={confirmOpen}
	title="Delete this map?"
	description={`“${pendingDelete?.topic ?? ''}” and every article it collected will be removed. This can't be undone.`}
	confirmLabel="Delete map"
	onconfirm={confirmDelete}
/>
