<script lang="ts">
	import { invalidate } from '$app/navigation';
	import { api, isRunning, type Analysis, type AnalysisEvent } from '#lib/api.ts';
	import { followAnalysis } from '#lib/api/stream.ts';
	import { formatDuration, plural } from '#lib/format.ts';
	import CircleSlash from '@lucide/svelte/icons/circle-slash';
	import FileText from '@lucide/svelte/icons/file-text';
	import Flag from '@lucide/svelte/icons/flag';
	import Search from '@lucide/svelte/icons/search';
	import Shapes from '@lucide/svelte/icons/shapes';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { toast } from 'svelte-sonner';

	let { analysis: initial }: { analysis: Analysis } = $props();

	// Live updates from the stream override the analysis we were loaded with.
	let live = $state<Analysis | null>(null);
	const analysis = $derived(live ?? initial);
	let events = $state<AnalysisEvent[]>([]);
	let cancelling = $state(false);
	let now = $state(Date.now());

	$effect(() => {
		const stop = followAnalysis(initial.id, {
			onAnalysis: (a) => {
				live = a;
				// Finished, failed or cancelled: reload the page data to show results.
				if (!isRunning(a)) invalidate('app:analysis');
			},
			onEvent: (e) => events.push(e),
			onGone: () => invalidate('app:analysis')
		});
		const tick = setInterval(() => (now = Date.now()), 1000);
		return () => {
			stop();
			clearInterval(tick);
		};
	});

	const elapsed = $derived((now - analysis.created_ts * 1000) / 1000);
	const indexed = $derived(events.filter((e) => e.kind === 'article').length);
	const skipped = $derived(events.filter((e) => e.kind === 'skip').length);
	const newestFirst = $derived([...events].reverse());

	async function cancel() {
		cancelling = true;
		try {
			await api.cancelAnalysis(analysis.id);
		} catch (e) {
			cancelling = false;
			toast.error(`Couldn't cancel: ${(e as Error).message}`);
		}
	}

	const ICONS = {
		stage: Flag,
		query: Search,
		article: FileText,
		skip: CircleSlash,
		cluster: Shapes,
		warning: TriangleAlert,
		error: TriangleAlert
	} as const;

	function domain(url: string | null): string {
		if (!url) return '';
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return '';
		}
	}
</script>

<section
	class="grid flex-1 gap-8 px-4 pb-10 sm:px-6 lg:grid-cols-[minmax(0,26rem)_1fr] lg:overflow-hidden"
>
	<div>
		<p class="text-lg font-medium" aria-live="polite">
			{analysis.stage_detail ?? 'Starting'}
		</p>
		<div
			class="mt-4 h-2 overflow-hidden rounded-full bg-rule-soft"
			role="progressbar"
			aria-label="Mapping progress"
			aria-valuemin={0}
			aria-valuemax={100}
			aria-valuenow={analysis.progress}
		>
			<div
				class="h-full rounded-full bg-accent transition-[width] duration-500"
				style:width="{analysis.progress}%"
			></div>
		</div>
		<dl class="mt-4 grid grid-cols-3 gap-4 text-sm">
			<div>
				<dt class="text-muted">Done</dt>
				<dd class="text-lg font-medium tabular">{analysis.progress}%</dd>
			</div>
			<div>
				<dt class="text-muted">Articles kept</dt>
				<dd class="text-lg font-medium tabular">{indexed}</dd>
			</div>
			<div>
				<dt class="text-muted">Elapsed</dt>
				<dd class="text-lg font-medium tabular">{formatDuration(elapsed)}</dd>
			</div>
		</dl>
		<p class="mt-6 max-w-sm text-sm text-ink-2">
			Most maps take 3 to 8 minutes. You can leave this page; the map keeps building and shows up in
			your list.
		</p>
		<button
			type="button"
			onclick={cancel}
			disabled={cancelling}
			class="mt-5 rounded-md border border-rule px-4 py-2 text-sm font-medium text-ink-2 hover:border-danger hover:text-danger disabled:opacity-50"
		>
			{cancelling ? 'Cancelling…' : 'Cancel this map'}
		</button>
	</div>

	<div class="flex min-h-0 flex-col">
		<h2 class="flex items-baseline justify-between border-b border-rule pb-2">
			<span class="font-semibold">Activity</span>
			<span class="text-sm text-muted tabular">
				{plural(indexed, 'article')} kept, {plural(skipped, 'page')} skipped
			</span>
		</h2>
		<ol class="min-h-0 flex-1 overflow-y-auto" aria-label="Pipeline activity, newest first">
			{#each newestFirst as e (e.id)}
				{@const Icon = ICONS[e.kind]}
				<li
					class="grid grid-cols-[1.25rem_1fr_auto] items-baseline gap-3 border-b border-rule-soft py-2 text-sm
						{e.kind === 'stage' ? 'font-medium text-ink' : 'text-ink-2'}"
				>
					<Icon
						size={14}
						class="translate-y-0.5 {e.kind === 'error' ? 'text-danger' : 'text-muted'}"
						aria-hidden="true"
					/>
					<span class="min-w-0 truncate">
						{#if e.kind === 'skip'}<span class="text-muted">Skipped:</span>{/if}
						{e.message}
					</span>
					<span class="truncate text-muted">{domain(e.url)}</span>
				</li>
			{:else}
				<li class="py-6 text-sm text-muted">Waiting for the first step…</li>
			{/each}
		</ol>
	</div>
</section>
